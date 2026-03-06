import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import web
from redis.asyncio import Redis

from src.bot.twitch_bot import TwitchBot
from src.core.config_loader import load_settings
from src.utils.token_manager import TokenManager

logger = logging.getLogger(__name__)

TaskType = asyncio.Task[None]


class BotManager:
    """
    Manage the lifecycle of a TwitchBot instance.

    Responsibilities:
      - Maintain and refresh OAuth tokens
      - Monitor Twitch WebSocket and EventSub health
      - Restart the bot if necessary
      - Provide an internal HTTP healthcheck endpoint
      - Schedule bot activity (offline/online) according to config
    """

    DEFAULT_SLEEP = 60
    WATCHDOG_SLEEP = 60
    SCHEDULE_LOOP_SLEEP = 60
    TOKEN_REFRESH_RETRY_SLEEP = 300
    STATUS_INTERVAL = 1800

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
    _status_task: TaskType | None

    def __init__(self, token_manager: TokenManager, redis: Redis) -> None:
        """
        Initialize BotManager.

        Args:
            token_manager: The TokenManager instance used to handle OAuth tokens.
            redis: An async Redis client instance for caching and persistence.
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
        self._status_task = None

    async def _periodic_status_report(self) -> None:
        """
        Periodically report the current bot status at fixed intervals.

        This task continuously calls `report_status()` every `self.status_interval`
        seconds. Exceptions during status reporting are caught and logged without
        stopping the loop. Intended to run as a background task while the bot is active.

        Returns:
            None
        """
        while True:
            try:
                await self.report_status()
            except Exception as e:
                logger.error(f"Failed to report status: {e}")
            await asyncio.sleep(self.STATUS_INTERVAL)

    async def report_status(self) -> None:
        """
        Gather and log the current status of the bot.

        The status report includes:
          - Whether the bot is active
          - Twitch WebSocket and IRC connection status
          - Configured and joined channels
          - EventSub subscription and active socket counts
          - Redis key count

        Accesses protected members via helper methods to reduce mypy warnings.

        Log a detailed summary of the bot state. Exceptions during
        data gathering are caught and logged; the function does not raise
        them externally.

        Returns:
            None
        """
        bot = self.bot
        if bot is None:
            logger.warning("Bot is not initialized; skipping status report")
            return

        active: bool | None = getattr(bot, "active", None)

        conn = self._get_ws_connection(bot)
        connected: bool = getattr(conn, "is_alive", False) if conn else False

        channels_configured: list[str] = []
        if hasattr(bot, "config") and bot.config:
            channels_configured = bot.config.get("channels", [])

        joined_count: int = 0
        if conn:
            initial_channels = getattr(conn, "_initial_channels", [])
            if isinstance(initial_channels, list):
                joined_count = len(initial_channels)

        irc_connected: bool = connected

        eventsub_status: dict[str, int | bool] = {"subscribed": False, "sockets": 0, "active": 0}
        es_client_sockets = self._get_eventsub_sockets(bot)
        eventsub = getattr(bot, "eventsub", None)
        if eventsub:
            eventsub_status["subscribed"] = getattr(eventsub, "subscribed", False)
            if es_client_sockets is not None:
                eventsub_status["sockets"] = len(es_client_sockets)
                eventsub_status["active"] = sum(1 for s in es_client_sockets if getattr(s, "is_connected", False))

        redis_keys_count: int | str = "N/A"
        try:
            if hasattr(bot, "redis") and bot.redis:
                info = await bot.redis.info()
                db0 = info.get("db0", {})
                if isinstance(db0, dict):
                    redis_keys_count = len(db0)
        except Exception as e:
            logger.warning(f"Redis error when counting keys: {e}")

        logger.info(
            "Bot Status Report:\n"
            f"  Active: {active}\n"
            f"  Connected (WebSocket IRC alive): {connected}\n"
            f"  Channels configured: {len(channels_configured)}\n"
            f"  Channels joined: {joined_count}\n"
            f"  EventSub: subscribed={eventsub_status['subscribed']}, "
            f"sockets={eventsub_status['sockets']}, active={eventsub_status['active']}\n"
            f"  WebSocket IRC: connected={irc_connected}, joined_channels={joined_count}\n"
            f"  Redis keys count: {redis_keys_count}"
        )

    @staticmethod
    def _get_ws_connection(bot: "TwitchBot") -> Any:
        """
        Safely get the bot's WebSocket connection.

        Args:
            bot: TwitchBot instance.

        Returns:
            The _connection object or None if not present.
        """
        return getattr(bot, "_connection", None)

    @staticmethod
    def _get_eventsub_sockets(bot: "TwitchBot") -> list[Any]:
        """
        Safely retrieve EventSub client sockets.

        Args:
            bot: TwitchBot instance.

        Returns:
            List of sockets or empty list if unavailable.
        """
        client = getattr(getattr(bot, "eventsub", None), "client", None)
        return getattr(client, "_sockets", [])

    async def start_health_server(self, host: str = "127.0.0.1", port: int = 8081) -> None:
        """
        Start an internal HTTP server to provide a healthcheck endpoint.

        The server exposes a `/health` route that reports the bot's status.

        Args:
            host: The hostname or IP address to bind the health server to.
            port: The port number to listen on for health requests.
        """
        self.health_app = web.Application()
        self.health_app.add_routes([web.get("/health", self._handle_health)])
        self.health_runner = web.AppRunner(self.health_app, access_log=None)
        await self.health_runner.setup()
        site = web.TCPSite(self.health_runner, host, port)
        await site.start()
        logger.info(f"Health server running on {host}:{port}")

    async def stop_health_server(self) -> None:
        """
        Stop the internal HTTP health server.

        Cleans up the web application runner and logs the shutdown.
        """
        if self.health_runner:
            await self.health_runner.cleanup()
            logger.info("Health server stopped")

    async def _handle_health(self, _: web.Request) -> web.Response:
        """
        Handle incoming `/health` HTTP requests.

        Checks if the bot is running and its WebSocket connection is healthy.

        Args:
            _: The aiohttp Request object (unused).

        Returns:
            web.Response: HTTP 200 with "OK" if the bot is healthy,
                          HTTP 500 with "UNHEALTHY" otherwise.
        """
        healthy = self._running and self.bot and getattr(self.bot, "is_connected", False)
        if healthy:
            ws_healthy = await self._check_websocket()
            if ws_healthy:
                return web.Response(text="OK", status=200)
        return web.Response(text="UNHEALTHY", status=500)

    async def start(self) -> None:
        """
        Start the bot and its background tasks.

        This method starts:
          - the token refresh loop,
          - the watchdog loop, and
          - the scheduled activity loop,
        as well as the internal health server.

        It also continuously attempts to start the TwitchBot instance,
        restarting it automatically on failure.
        """
        self._running = True
        await self.start_health_server(host="0.0.0.0", port=8081)

        self.refresh_task = asyncio.create_task(self._token_refresh_loop())
        self.watchdog_task = asyncio.create_task(self._watchdog_loop())
        self.scheduled_task = asyncio.create_task(self._scheduled_activity_loop())
        self._status_task = asyncio.create_task(self._periodic_status_report())

        while self._running:
            try:
                token = await self.token_manager.get_access_token("BOT_TOKEN")
                self.bot = TwitchBot(self.token_manager, token, redis=self.redis)
                self.bot_task = asyncio.create_task(self.bot.start())
                self.bot.manager = self
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
        Safely restart the bot.

        Closes EventSub, cancels the current bot task if running, closes the bot,
        re-initializes the TwitchBot instance, and starts it again. Acquires a lock
        to prevent concurrent restarts and resets the WebSocket error count.

        Ensures the bot is either restarted and connected, or logs warnings if it fails
        to reconnect.

        Returns:
            None
        """
        async with self._restart_lock:
            if not self._running:
                return

            logger.warning("Restarting bot...")

            if self.bot and hasattr(self.bot, "eventsub") and self.bot.eventsub:
                try:
                    await self.bot.eventsub.close()
                except Exception as e:
                    logger.warning(f"Error closing EventSub during restart: {e}")

            if self.bot_task and not self.bot_task.done():
                self.bot_task.cancel()
                try:
                    await self.bot_task
                except asyncio.CancelledError:
                    logger.debug("Bot task cancelled")
                except Exception as e:
                    logger.warning(f"Error during bot task cancellation: {e}")

            self.bot_task = None
            if self.bot:
                try:
                    await self.bot.close()
                except Exception as e:
                    logger.warning(f"Error while closing bot: {e}")
            self.bot = None
            await asyncio.sleep(2)

            try:
                token = await self.token_manager.get_access_token("BOT_TOKEN")
                self.bot = TwitchBot(self.token_manager, token, redis=self.redis)
                self.bot_task = asyncio.create_task(self.bot.start())
                self.bot.manager = self
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
        Stop the bot and all associated background tasks.

        Stops the health server, cancels all running background tasks
        (token refresh, watchdog, bot task, scheduled activity), and closes
        both the bot and Redis connections. Ensures a clean shutdown of the
        BotManager.

        Returns:
            None
        """
        self._running = False
        await self.stop_health_server()

        tasks: list[TaskType] = []

        for t in (self.refresh_task, self.watchdog_task, self.bot_task, self.scheduled_task, self._status_task):
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

        Sleeps for the configured refresh delay, then refreshes the bot token.
        If a streamer token exists, refreshes it as well. Updates the bot's
        API headers after refreshing tokens.

        Handles exceptions by logging them and retrying after a delay.
        Exits cleanly if the task is canceled.

        Returns:
            None
        """
        while self._running:
            settings = load_settings()
            delay = settings.get("refresh_token_interval", 7200)

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
                await asyncio.sleep(self.TOKEN_REFRESH_RETRY_SLEEP)

    async def _watchdog_loop(self) -> None:
        """
        Continuously monitor bot health and coordinate recovery strategy.

        This loop periodically checks overall bot health:
          - WebSocket liveness (with ping/pong validation),
          - IRC channel connectivity,
          - EventSub socket state.

        Recovery strategy:

          1. On the first detected failure:
             - Allow TwitchIO's internal re-connect logic to attempt recovery.
             - Wait 60 seconds before performing another health check.
             - This prevents conflict with the framework's own re-connect mechanism.

          2. If a second consecutive failure occurs:
             - Consider the connection unrecoverable.
             - Trigger a full bot restart.

        The failure counter resets immediately after a successful health check.

        This design:
          - Respects TwitchIO’s internal reconnect/backoff system.
          - Prevents long-lived zombie WebSocket states.
          - Avoids aggressive restart loops.
          - Guarantees recovery within a bounded time window.

        The loop runs while the BotManager is active.
        """
        while self._running:
            try:
                hour = datetime.now().astimezone().hour
                if 1 <= hour < 7:
                    check_interval = 180
                else:
                    check_interval = 120

                await asyncio.sleep(check_interval)

                healthy = await self._check_bot_health()

                if healthy:
                    if self._websocket_error_count > 0:
                        logger.info("WebSocket recovered successfully")
                    self._websocket_error_count = 0
                    continue

                self._websocket_error_count += 1
                logger.warning(f"WebSocket unhealthy " f"({self._websocket_error_count} consecutive failure(s))")

                # ---- First failure: allow TwitchIO internal reconnect ----
                if self._websocket_error_count == 1:
                    logger.info("Allowing TwitchIO internal reconnect logic " "to recover (60s grace period)")
                    await asyncio.sleep(self.WATCHDOG_SLEEP)
                    continue

                # ---- Second consecutive failure: force restart ----
                logger.error("WebSocket did not recover — performing full restart")
                await self.restart_bot()
                self._websocket_error_count = 0

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.exception(f"Error in watchdog loop: {e}")
                await asyncio.sleep(self.WATCHDOG_SLEEP)

    async def _check_bot_health(self) -> bool:
        """
        Check the health of the bot, including Twitch WebSocket and EventSub.

        Verifies that the bot is connected, that the WebSocket is active,
        that all expected channels are joined, and that EventSub has at least
        one active socket. If EventSub is unhealthy, attempts recovery via
        ensure_alive() and returns False to trigger watchdog escalation.

        Returns:
            bool: True if the bot and all critical connections are healthy, False otherwise.
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
                    logger.warning("EventSub health check failed – attempting recovery")
                    try:
                        await self.bot.eventsub.ensure_alive()
                    except Exception as e:
                        logger.error(f"Error during EventSub recovery: {e}")
                    return False

            return True

        except Exception as e:
            logger.exception(f"Error during _check_bot_health: {e}")
            return False

    async def _check_eventsub(self) -> bool:
        """
        Check the health of the EventSub WebSocket client.

        Confirm that the EventSub client exists and has at least one active
        connected socket. Log warnings if no active sockets are found.

        Returns:
            bool: True if there is at least one active EventSub socket, False otherwise.
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
                sockets = self._get_eventsub_sockets(self.bot)
                if not sockets:
                    logger.debug("No EventSub sockets found")
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
        Validate TwitchIO WebSocket liveness.

        Performs structural checks and a ping round-trip to ensure the
        underlying aiohttp WebSocket is responsive.

        Returns:
            bool: True if the socket is alive and responsive, False otherwise.
        """
        if not self.bot:
            return False

        try:
            if not getattr(self.bot, "is_connected", False):
                return False

            connection = self._get_ws_connection(self.bot)
            if not connection:
                return False

            ws = getattr(connection, "_websocket", None)
            if not ws:
                return False

            if ws.closed or ws.close_code is not None:
                return False

            try:
                await asyncio.wait_for(ws.ping(), timeout=5.0)
            except (TimeoutError, ConnectionError, RuntimeError, OSError):
                return False

            writer = getattr(ws, "_writer", None)
            transport = getattr(writer, "transport", None)
            if transport and transport.is_closing():
                return False

            return True

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Error checking websocket: {e}")
            return False

    @staticmethod
    def _in_offline_window(now: time, start: time, end: time) -> bool:
        """
        Determine if the current time falls within the offline window.

        Handles windows that cross midnight (e.g., 19:00–06:00).

        Args:
            now: Current time.
            start: Start of the offline period.
            end: End of the offline period.

        Returns:
            True if `now` is within the window, False otherwise.
        """
        if start < end:
            return start <= now < end
        return now >= start or now < end

    async def _get_schedule_config(self) -> tuple[time, time, ZoneInfo] | None:
        """
        Extract schedule parameters from the bot's configuration.

        Returns:
            A tuple (offline_from, offline_to, timezone) if the schedule is enabled
            and all required fields are present; otherwise None.
        """
        if not self.bot:
            return None
        schedule = self.bot.config.get("schedule", {})
        if not schedule.get("enabled"):
            return None
        off_time = schedule.get("offline_from")
        on_time = schedule.get("offline_to")
        timezone = schedule.get("timezone")
        if not off_time or not on_time or not timezone:
            return None
        return off_time, on_time, ZoneInfo(timezone)

    async def _should_be_offline(self, now_dt: datetime, off_time: time, on_time: time) -> bool:
        """
        Determine whether the bot should be offline at the given moment.

        The decision is based on the schedule and any admin override stored in Redis.
        An override for today disables the schedule entirely for that day.

        Args:
            now_dt: Current date and time (timezone-aware).
            off_time: Start of the offline window.
            on_time: End of the offline window.

        Returns:
            True if the bot should be offline, False otherwise.
        """
        today_str = str(now_dt.date())
        override_key = f"bot:override:{today_str}"
        override = await self.redis.get(override_key)
        if override:
            return False
        return self._in_offline_window(now_dt.time(), off_time, on_time)

    async def _enter_offline_mode(self, bot: TwitchBot, now_dt: datetime, tz: ZoneInfo) -> None:
        """
        Transition the bot into offline mode.

        Deactivates the bot, sends a notification message (if not already sent today),
        and records in Redis that the message has been sent.

        Args:
            bot: The TwitchBot instance.
            now_dt: Current date and time (timezone-aware).
            tz: Timezone object for calculating end‑of‑day.
        """
        if not bot.active:
            return
        bot.active = False
        logger.info(f"[{now_dt}] Entering scheduled offline window")

        today_str, seconds_until_end_of_day = self._get_today_keys(tz)
        message_key = f"bot:schedule_msg:{today_str}"
        message_sent = await self.redis.get(message_key)
        if not message_sent:
            for channel in bot.connected_channels:
                try:
                    await channel.send("Bot is entering scheduled sleep mode. Use !ботговори to wake it (admin only).")
                except Exception as e:
                    logger.error(f"Failed to send sleep message: {e}")
                    self._websocket_error_count += 1

            await self.redis.set(message_key, "1", ex=seconds_until_end_of_day)

    async def _exit_offline_mode(self, bot: TwitchBot, now_dt: datetime) -> None:
        """
        Transition the bot into online mode.

        Activates the bot, ensures it is running (restarting if necessary),
        sends a wake‑up notification, and removes the Redis marker for today's message.

        Args:
            bot: The TwitchBot instance.
            now_dt: Current date and time (timezone-aware).
        """
        if bot.active:
            return

        bot.active = True
        logger.info(f"[{now_dt}] Scheduled wake-up triggered")

        if self.bot_task is None or self.bot_task.done() or not getattr(bot, "is_connected", False):
            logger.warning("Bot not running after sleep, restarting...")
            await self.restart_bot()

            if self.bot is None or not getattr(self.bot, "is_connected", False):
                logger.error("Bot failed to restart or is not connected")
                return
            bot = self.bot

        for channel in bot.connected_channels:
            try:
                await channel.send("Bot is now active.")
            except Exception as e:
                logger.error(f"Failed to send wake-up message: {e}")
                self._websocket_error_count += 1

        today_str = str(now_dt.date())
        message_key = f"bot:schedule_msg:{today_str}"
        await self.redis.delete(message_key)

    async def _scheduled_activity_loop(self) -> None:
        """
        Control bot activity based on schedule and admin override.

        This loop runs continuously while the manager is active.
        It checks the schedule at regular intervals (every 60 seconds)
        and puts the bot to sleep or wakes it up accordingly.

        Returns:
            None
        """
        while self._running:
            try:
                if not self.bot:
                    await asyncio.sleep(5)
                    continue

                config = await self._get_schedule_config()
                if config is None:
                    await asyncio.sleep(self.SCHEDULE_LOOP_SLEEP)
                    continue

                off_time, on_time, tz = config
                now_dt = datetime.now(tz)

                should_be_offline = await self._should_be_offline(now_dt, off_time, on_time)

                if should_be_offline:
                    await self._enter_offline_mode(self.bot, now_dt, tz)
                else:
                    await self._exit_offline_mode(self.bot, now_dt)

                await asyncio.sleep(self.SCHEDULE_LOOP_SLEEP)

            except Exception as e:
                logger.exception(f"Scheduled activity loop error: {e}")
                await asyncio.sleep(self.SCHEDULE_LOOP_SLEEP)

    async def set_bot_sleep(self) -> None:
        """
        Deactivate the bot for today as an admin override.

        This command sets a Redis key for today to indicate the override.
        The bot will remain inactive until the end of the current day.

        Returns:
            None
        """
        if not self.bot:
            return

        schedule = self.bot.config.get("schedule", {})
        timezone = schedule.get("timezone")
        if not timezone:
            logger.warning("Timezone not configured, cannot set sleep")
            return

        tz = ZoneInfo(timezone)
        today_str, seconds_until_end_of_day = self._get_today_keys(tz)
        override_key = f"bot:override:{today_str}"

        await self.redis.set(override_key, "1", ex=seconds_until_end_of_day)
        self.bot.active = False

        for channel in self.bot.connected_channels:
            await channel.send("banka Алибидерчи! Бот выключен до конца дня.")

        logger.info(f"Bot set to sleep (override) until midnight ({today_str})")

    async def set_bot_wake(self) -> None:
        """
        Activate the bot and cancel today's override.

        This command deletes the Redis override key for today.
        The bot will resume normal operation immediately.

        Returns:
            None
        """
        if not self.bot:
            return

        schedule = self.bot.config.get("schedule", {})
        timezone = schedule.get("timezone")
        if not timezone:
            logger.warning("Timezone not configured, cannot wake bot")
            return

        tz = ZoneInfo(timezone)
        today_str, _ = self._get_today_keys(tz)
        override_key = f"bot:override:{today_str}"
        await self.redis.delete(override_key)

        self.bot.active = True
        for channel in self.bot.connected_channels:
            await channel.send("deshovka Бот снова активен!")

        logger.info(f"Bot activated (override cleared) for {today_str}")

    @staticmethod
    def _get_today_keys(tz: ZoneInfo) -> tuple[str, int]:
        """
        Get Redis key for today and seconds until the end of the day.

        Args:
            tz (ZoneInfo): Timezone object for calculating the end of day.

        Returns:
            tuple[str, int]: Tuple containing:
                - Redis key for today's date as a string.
        """
        now = datetime.now(tz)
        today_str = str(now.date())
        tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=tz)
        seconds_until_end_of_day = int((tomorrow - now).total_seconds())
        return today_str, seconds_until_end_of_day
