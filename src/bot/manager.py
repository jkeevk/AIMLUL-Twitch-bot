import asyncio
import logging
from typing import Optional

from bot.twitch_bot import TwitchBot
from src.utils.token_manager import TokenManager

logger = logging.getLogger(__name__)

TaskType = asyncio.Task[None]


class BotManager:
    """
    Manage TwitchBot lifecycle, token refresh and watchdog monitoring.
    """

    token_manager: TokenManager
    bot: Optional[TwitchBot]
    _running: bool
    _restart_lock: asyncio.Lock

    refresh_task: Optional[TaskType]
    watchdog_task: Optional[TaskType]
    bot_task: Optional[TaskType]

    _websocket_error_count: int

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

    async def start(self) -> None:
        """
        Start the bot and background tasks.

        Args:
            None.
        """
        self._running = True

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
        Stop bot and all background tasks.

        Args:
            None.
        """
        self._running = False

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
        delay: int = 7200

        while self._running:
            try:
                if self.bot and "refresh_token_delay_time" in self.bot.config:
                    delay = int(self.bot.config["refresh_token_delay_time"])

                await asyncio.sleep(delay)

                logger.info("Refreshing tokens...")
                await self.token_manager.refresh_access_token("BOT_TOKEN")

                if self.token_manager.has_streamer_token():
                    await self.token_manager.refresh_access_token("STREAMER_TOKEN")

                logger.info("Tokens refreshed")

            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Token refresh failed")
                await asyncio.sleep(300)

    async def _watchdog_loop(self) -> None:
        """
        Monitor bot health and restart on failures.

        Args:
            None.
        """
        CHECK_INTERVAL = 60

        while self._running:
            await asyncio.sleep(CHECK_INTERVAL)

            healthy = await self._check_bot_health()

            if not healthy:
                self._websocket_error_count += 1
                logger.warning(f"WebSocket unhealthy ({self._websocket_error_count}/3)")

                if self._websocket_error_count >= 3:
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

            return await self._check_websocket()

        except Exception:
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

        except Exception:
            return False
