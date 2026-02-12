import asyncio
import logging
from datetime import datetime

from aiohttp import web
from redis.asyncio import Redis

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
    scheduled_task: TaskType | None

    def __init__(self, token_manager: TokenManager, redis: Redis) -> None:
        """
        Initialize BotManager.

        Args:
            token_manager: Token manager instance.
            redis: Redis instance.
        """
        self.token_manager = token_manager
        self.redis = redis
        self.bot = None
        self._running = False
        self._restart_lock = asyncio.Lock()
        self.refresh_task = None
        self.watchdog_task = None
        self.bot_task = None
        self._websocket_error_count = 0
        self.health_app = None
        self.health_runner = None
        self.scheduled_task = None

    async def start_health_server(self, host: str = "127.0.0.1", port: int = 8081) -> None:
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
        self.scheduled_task = asyncio.create_task(self._scheduled_activity_loop())

        while self._running:
            try:
                token = await self.token_manager.get_access_token("BOT_TOKEN")
                self.bot = TwitchBot(self.token_manager, token, redis=self.redis)
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
                    logger.debug("Bot task cancelled")
                except Exception as e:
                    logger.warning(f"Error during bot task cancellation: {e}")

            self.bot_task = None
            self.bot = None
            await asyncio.sleep(2)

            try:
                token = await self.token_manager.get_access_token("BOT_TOKEN")
                self.bot = TwitchBot(self.token_manager, token, redis=self.redis)
                self.bot_task = asyncio.create_task(self.bot.start())
                self._websocket_error_count = 0

                await asyncio.sleep(10)

                if self.bot and getattr(self.bot, "is_connected", False):
                    logger.info("Bot restarted successfully")
                else:
                    logger.warning("Bot restarted but not connected yet")

            except Exception as e:
                logger.error(f"Failed to restart bot: {e}", exc_info=True)
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

        for t in (self.refresh_task, self.watchdog_task, self.bot_task, self.scheduled_task):
            if t and not t.done():
                t.cancel()
                tasks.append(t)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if self.bot:
            await self.bot.close()
        if self.redis:
            await self.redis.aclose()
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
        """Monitor Twitch WebSocket health and restart the bot on repeated failures."""
        while self._running:
            try:
                hour = datetime.now().astimezone().hour
                if 1 <= hour < 7:
                    max_failures = 5
                    check_interval = 300
                    restart_delay = 30
                else:
                    max_failures = 3
                    check_interval = 120
                    restart_delay = 15

                await asyncio.sleep(check_interval)

                healthy = await self._check_bot_health()
                if healthy and self.bot and hasattr(self.bot, "eventsub"):
                    try:
                        await self.bot.eventsub.ensure_alive()
                    except Exception as e:
                        logger.warning(f"Error ensuring EventSub alive: {e}")
                if not healthy:
                    self._websocket_error_count += 1
                    logger.warning(f"WebSocket unhealthy ({self._websocket_error_count}/{max_failures})")

                    if self._websocket_error_count == 1:
                        logger.info("Giving bot time to self-recover...")
                        await asyncio.sleep(60)
                        healthy = await self._check_bot_health()
                        if healthy:
                            logger.info("Bot recovered automatically")
                            self._websocket_error_count = 0
                            continue

                    if self._websocket_error_count >= max_failures:
                        logger.error(f"Critical WebSocket errors → restarting bot in {restart_delay}s")
                        await asyncio.sleep(restart_delay)
                        await self.restart_bot()
                        self._websocket_error_count = 0
                else:
                    self._websocket_error_count = 0

            except Exception as e:
                logger.exception(f"Error in watchdog loop: {e}")
                await asyncio.sleep(60)

    async def _check_bot_health(self) -> bool:
        """
        Check bot connection, Twitch WebSocket, and EventSub WebSocket health.

        Returns:
            True if all critical WS are healthy, False otherwise.
        """
        if not self.bot:
            logger.debug("Bot not initialized in health check")
            return False

        try:
            if not getattr(self.bot, "is_connected", False):
                logger.debug("Bot is_connected = False")
                return False

            ws_ok = await self._check_websocket()
            if not ws_ok:
                logger.debug("WebSocket check failed")
                return False

            expected_channels = self.bot.config.get("channels", [])
            if not expected_channels:
                logger.error("No channels configured in TwitchBot")
                return False

            expected = {c.lower() for c in expected_channels}
            actual = {c.name.lower() for c in self.bot.connected_channels}
            missing = expected - actual

            if missing:
                logger.debug(f"Missing channels (might be temporary): {missing}")
                if len(actual) == 0:
                    logger.warning("Not connected to any channels")
                    return False
                logger.info(f"Connected to {len(actual)}/{len(expected)} channels")

            if hasattr(self.bot, "eventsub") and self.bot.eventsub:
                eventsub_ok = await self._check_eventsub()
                if not eventsub_ok:
                    logger.warning("EventSub health check failed")

            return True

        except Exception as e:
            logger.exception(f"Error during _check_bot_health: {e}")
            return False

    async def _check_eventsub(self) -> bool:
        """Check the health of the EventSub WebSocket client.

        Returns:
            True if there is at least one active EventSub socket, otherwise False.
        """
        try:
            if not self.bot:
                return False
            eventsub = self.bot.eventsub

            if not hasattr(eventsub, "client") or not eventsub.client:
                logger.debug("EventSub client not initialized")
                return False

            client = eventsub.client

            if hasattr(client, "_sockets"):
                sockets = client._sockets
                if not sockets:
                    logger.debug("No EventSub sockets")
                    return False

                active_sockets = [s for s in sockets if hasattr(s, "is_connected") and s.is_connected]
                if not active_sockets:
                    logger.debug("No active EventSub sockets")
                    return False

                logger.debug(f"EventSub has {len(active_sockets)} active sockets")
                return True

            return False

        except Exception as e:
            logger.warning(f"Error checking EventSub: {e}")
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
            if not getattr(self.bot, "is_connected", False):
                logger.debug("Bot is_connected = False")
                return False

            connection = getattr(self.bot, "_connection", None)
            if connection and hasattr(connection, "connected"):
                if not connection.connected:
                    logger.debug("Connection.connected = False")
                    return False

            if hasattr(self.bot, "connected_channels") and not self.bot.connected_channels:
                logger.debug("No connected channels — WS likely dead")
                return False

            return True

        except Exception as e:
            logger.warning(f"Error checking websocket: {e}")
            return False

    async def _scheduled_activity_loop(self) -> None:
        """
        Manage the bot's activity according to a schedule.

        This coroutine runs continuously and checks whether the current time
        falls within the configured offline window. It will automatically
        deactivate the bot and send an offline message if necessary. It also
        persists the last shutdown in the database to avoid sending repeated
        messages on bot restarts.

        The offline window can be overridden manually by an admin using commands.
        """
        from datetime import time as dtime
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        def in_offline_window(time_to_check: dtime, start: dtime, end: dtime) -> bool:
            """
            Check if the current time falls within the offline window.

            Args:
                time_to_check (dtime): The time to check.
                start (dtime): The start time of the offline window.
                end (dtime): The end time of the offline window.

            Returns:
                bool: True if time_to_check is within the window, False otherwise.
            """
            if start < end:
                return start <= time_to_check < end
            return time_to_check >= start or time_to_check < end

        while self._running:
            if not self.bot or not getattr(self.bot, "is_connected", False):
                await asyncio.sleep(5)
                continue

            bot = self.bot
            schedule = bot.config.get("schedule", {})
            if not schedule.get("enabled"):
                await asyncio.sleep(60)
                continue

            off_time = schedule.get("offline_from")
            on_time = schedule.get("offline_to")
            timezone = schedule.get("timezone")

            if not off_time or not on_time or not timezone:
                await asyncio.sleep(60)
                continue

            try:
                tz = ZoneInfo(timezone)
            except ZoneInfoNotFoundError:
                await asyncio.sleep(60)
                continue

            now_dt = datetime.now(tz)
            now_time = now_dt.time()
            today = now_dt.date()

            assert bot.db is not None
            record = await bot.db.get_scheduled_offline(today)
            message_already_sent = record.sent_message if record else False

            if not getattr(bot, "manual_override", False) and in_offline_window(now_time, off_time, on_time):
                if not getattr(bot, "scheduled_offline", False):
                    bot.active = False
                    bot.scheduled_offline = True

                if not message_already_sent:
                    for channel in getattr(bot, "connected_channels", []):
                        await channel.send(
                            "Bedge отключаюсь на время киношного. "
                            "Разбудить: !ботговори Заткнуть: !ботзаткнись (admin only)"
                        )
                    await bot.db.set_scheduled_offline(today, sent_message=True)

            else:
                if getattr(bot, "scheduled_offline", False) or message_already_sent:
                    bot.scheduled_offline = False
                    bot.manual_override = False

                    if not getattr(bot, "active", True):
                        bot.active = True
                        for channel in getattr(bot, "connected_channels", []):
                            await channel.send("peepoArrive работаем")

                    if getattr(bot, "db", None):
                        await bot.db.set_scheduled_offline(today, sent_message=False)

            await asyncio.sleep(60)
