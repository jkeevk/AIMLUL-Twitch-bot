import asyncio
import logging
from datetime import datetime

from aiohttp import web

from src.bot.twitch_bot import TwitchBot
from src.core.config_loader import load_settings
from src.utils.token_manager import TokenManager

logger = logging.getLogger(__name__)

TaskType = asyncio.Task[None]


class BotManager:
    """Manage TwitchBot lifecycle, token refresh, watchdog monitoring, and healthcheck."""

    token_manager: TokenManager
    bot: TwitchBot | None
    _running: bool
    _restart_lock: asyncio.Lock

    refresh_task: TaskType | None
    watchdog_task: TaskType | None
    bot_task: TaskType | None

    _websocket_error_count: int

    health_app: web.Application | None
    health_runner: web.AppRunner | None

    def __init__(self, token_manager: TokenManager) -> None:
        """
        Initialize BotManager.

        Args:
            token_manager: Token manager instance.
        """
        self.token_manager = token_manager
        self.bot = None
        self._running = False
        self._restart_lock = asyncio.Lock()
        self.refresh_task = None
        self.watchdog_task = None
        self.bot_task = None
        self._websocket_error_count = 0
        self.health_app = None
        self.health_runner = None

    async def start_health_server(self, host: str = "0.0.0.0", port: int = 8081) -> None:
        """
        Start an internal HTTP server for health checking.

        Args:
            host: Host to bind the health server to.
            port: Port to listen for health requests.
        """
        self.health_app = web.Application()
        self.health_app.add_routes([web.get("/health", self._handle_health)])
        self.health_runner = web.AppRunner(self.health_app, access_log=None)
        await self.health_runner.setup()
        site = web.TCPSite(self.health_runner, host, port)
        await site.start()
        logger.info(f"Health server running on {host}:{port}")

    async def stop_health_server(self) -> None:
        """Stop the internal health HTTP server."""
        if self.health_runner:
            await self.health_runner.cleanup()
            logger.info("Health server stopped")

    async def _handle_health(self, _: web.Request) -> web.Response:
        """
        Handle /health HTTP requests.

        Args:
            _: aiohttp request object (not used).

        Returns:
            HTTP 200 OK if bot is healthy, HTTP 500 UNHEALTHY otherwise.
        """
        healthy = self._running and self.bot and getattr(self.bot, "is_connected", False)
        if healthy:
            ws_healthy = await self._check_websocket()
            if ws_healthy:
                return web.Response(text="OK", status=200)
        return web.Response(text="UNHEALTHY", status=500)

    async def start(self) -> None:
        """
        Start the bot and background tasks.

        Starts token refresh, watchdog loop and health server.

        Args:
            None.
        """
        self._running = True
        await self.start_health_server(host="0.0.0.0", port=8081)

        self.refresh_task = asyncio.create_task(self._token_refresh_loop())
        self.watchdog_task = asyncio.create_task(self._watchdog_loop())

        while self._running:
            try:
                token = await self.token_manager.get_access_token("BOT_TOKEN")
                self.bot = TwitchBot(self.token_manager, token)
                self.bot_task = asyncio.create_task(self.bot.start())

                logger.info("Bot started")
                await self.bot_task

            except asyncio.CancelledError:
                logger.info("Bot task cancelled for restart")
                break

            except Exception as e:
                logger.exception(f"Bot crashed: {e}")
                await asyncio.sleep(10)

    async def restart_bot(self) -> None:
        """
        Restart the bot safely.

        Args:
            None.
        """
        async with self._restart_lock:
            if not self._running:
                return

            logger.warning("Restarting bot...")

            if self.bot_task and not self.bot_task.done():
                self.bot_task.cancel()
                try:
                    await self.bot_task
                except asyncio.CancelledError:
                    pass

            self.bot_task = None
            self.bot = None
            await asyncio.sleep(2)

            try:
                token = await self.token_manager.get_access_token("BOT_TOKEN")
                self.bot = TwitchBot(self.token_manager, token)
                self.bot_task = asyncio.create_task(self.bot.start())
                self._websocket_error_count = 0
                logger.info("Bot restarted successfully")

            except Exception as e:
                logger.error(f"Failed to restart bot: {e}")
                self.bot = None
                self.bot_task = None

    async def stop(self) -> None:
        """
        Stop bot and all background tasks, including health server.

        Args:
            None.
        """
        self._running = False
        await self.stop_health_server()

        tasks: list[TaskType] = []

        for t in (self.refresh_task, self.watchdog_task, self.bot_task):
            if t and not t.done():
                t.cancel()
                tasks.append(t)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if self.bot:
            await self.bot.close()

        logger.info("BotManager stopped")

    async def _token_refresh_loop(self) -> None:
        """
        Periodically refresh OAuth tokens.

        Args:
            None.
        """
        while self._running:
            settings = load_settings()
            delay = settings.get("refresh_token_delay_time", 7200)

            try:
                await asyncio.sleep(delay)

                await self.token_manager.refresh_access_token("BOT_TOKEN")
                bot_preview = self.token_manager.tokens["BOT_TOKEN"].access_token
                bot_preview = f"{bot_preview[:5]}...{bot_preview[-5:]}" if bot_preview else "empty"

                if self.token_manager.has_streamer_token():
                    await self.token_manager.refresh_access_token("STREAMER_TOKEN")
                    streamer_preview = self.token_manager.tokens["STREAMER_TOKEN"].access_token
                    streamer_preview = (
                        f"{streamer_preview[:5]}...{streamer_preview[-5:]}" if streamer_preview else "empty"
                    )
                    logger.info(
                        f"[Planned]: Tokens refreshed. BOT_TOKEN={bot_preview}, STREAMER_TOKEN={streamer_preview}"
                    )
                else:
                    logger.info(f"[Planned]: Tokens refreshed. BOT_TOKEN={bot_preview}")

                if self.bot and hasattr(self.bot, "api") and self.bot.api:
                    await self.bot.api.refresh_headers()

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.exception(f"Token refresh failed: {e}")
                await asyncio.sleep(300)

    async def _watchdog_loop(self) -> None:
        """Monitor bot health with time-sensitive thresholds."""
        while self._running:
            hour = datetime.now().astimezone().hour
            # Night (01:00-07:00):
            if 1 <= hour < 7:
                await asyncio.sleep(300)
                max_failures = 5
            else:
                await asyncio.sleep(60)
                max_failures = 3

            if not await self._check_bot_health():
                self._websocket_error_count += 1
                logger.warning(f"WebSocket unhealthy ({self._websocket_error_count}/{max_failures})")

                if self._websocket_error_count >= max_failures:
                    logger.error("Critical WebSocket errors → restart bot")
                    await self.restart_bot()
            else:
                self._websocket_error_count = 0

    async def _check_bot_health(self) -> bool:
        """
        Check bot connection and WebSocket health.

        Args:
            None.

        Returns:
            True if the bot is healthy, False otherwise.
        """
        if not self.bot:
            return False
        try:
            if not getattr(self.bot, "is_connected", False):
                return False

            expected_channels = self.bot.config.get("channels", [])

            if not expected_channels:
                logger.error("No channels configured in TwitchBot, but connection is up.")
                return False

            expected = {c.lower() for c in expected_channels}
            actual = {c.name.lower() for c in self.bot.connected_channels}

            missing = expected - actual

            if missing:
                logger.warning(f"Bot connected but failed to join channels: {missing}")
                return False

            return await self._check_websocket()

        except Exception as e:
            logger.exception(f"Error during _check_bot_health: {e}")
            return False

    async def _check_websocket(self) -> bool:
        """
        Check internal TwitchIO WebSocket state.

        Args:
            None.

        Returns:
            True if WS is active, False otherwise.
        """
        if not self.bot:
            return False
        try:
            ws = getattr(self.bot, "_ws", None)
            if ws is not None:
                return not ws.closed

            conn = getattr(self.bot, "_connection", None)
            if conn:
                ws2 = getattr(conn, "_websocket", None)
                if ws2 is not None:
                    return not ws2.closed

            return True
        except Exception as e:
            logger.exception(f"Error during _check_websocket: {e}")
            return False
