import logging
import os
import time
from contextlib import suppress
from typing import Any

from twitchio import Message
from twitchio.ext import commands

from src.api.twitch_api import TwitchAPI
from src.commands.command_handler import CommandHandler
from src.commands.permissions import is_admin
from src.commands.triggers.text_triggers import build_triggers
from src.core.config_loader import load_settings
from src.db.database import Database
from src.eventsub.handlers import handle_eventsub_reward
from src.eventsub.manager import EventSubManager
from src.utils.token_manager import TokenManager

logger = logging.getLogger(__name__)


class TwitchBot(commands.Bot):  # type: ignore[misc]
    """Main Twitch bot class handling commands, events, and EventSub integrations."""

    config: dict[str, Any]
    token_manager: TokenManager
    active: bool
    api: TwitchAPI
    db: Database | None
    command_handler: CommandHandler
    eventsub: EventSubManager
    triggers: dict[str, Any]

    def __init__(self, token_manager: TokenManager, bot_token: str) -> None:
        """
        Initialize the Twitch bot.

        Args:
            token_manager: Manager for handling token refresh operations
            bot_token: Bot authentication token
        """
        self.config = load_settings()
        self.token_manager = token_manager
        self.active = True

        super().__init__(
            token=bot_token,
            client_id=token_manager.tokens["BOT_TOKEN"].client_id,
            client_secret=token_manager.tokens["BOT_TOKEN"].client_secret,
            prefix="!",
            initial_channels=self.config["channels"],
        )

        self.api = TwitchAPI(self)

        dsn: str | None = os.getenv("DATABASE_URL") or self.config["database"].get("dsn")
        self.db = Database(dsn) if dsn else None

        self.command_handler = CommandHandler(self)
        self.eventsub = EventSubManager(self)
        self.triggers = build_triggers(self)
        self.token_refresh_task = None
        self.is_connected: bool = False
        self.scheduled_offline: bool = False
        self.manual_override: bool = False

    async def event_token_expired(self) -> str | None:
        """
        Called by TwitchIO when the EventSub token has expired or is invalid.

        Returns:
            A fresh STREAMER token or None if token refresh failed
        """
        try:
            token = await self.token_manager.get_streamer_token()
            logger.info("Streamer token for EventSub updated")
            return token
        except Exception as e:
            logger.error(f"Failed to refresh streamer token for EventSub: {e}")
            return None

    async def event_ready(self) -> None:
        """Called when the bot is ready and connected to Twitch."""
        logger.info("Bot ready")
        self.is_connected = True

        if self.db:
            try:
                await self.db.connect()
            except Exception as e:
                logger.error("DB connection failed", exc_info=e)
                self.db = None

        await self.eventsub.setup()
        self.loop.create_task(self.scheduled_activity_controller())

    async def event_message(self, message: Message) -> None:
        """
        Handle incoming chat messages.

        Args:
            message: The incoming message object
        """
        if message.echo:
            return

        if not self.active and not (message.author and is_admin(self, message.author.name)):
            return

        text = message.content.lower()

        for kw in self.triggers["gnome_keywords"]:
            if kw in text:
                await self.triggers["handlers"]["gnome"](message)
                return

        for kw in self.triggers["apple_keywords"]:
            if kw in text:
                await self.triggers["handlers"]["apple"](message)
                return

        await self.handle_commands(message)
        logger.info(f"{message.author.name}: {message.content}")

    async def event_eventsub_notification_channel_reward_redeem(self, event: Any) -> None:
        """
        Handle EventSub channel point reward redemption events.

        Args:
            event: The EventSub reward redemption event
        """
        if not self.active:
            return
        await handle_eventsub_reward(event, self)

    @commands.command(name="жопа")
    async def butt(self, ctx: commands.Context) -> None:
        """Handle the butt command."""
        if self.active:
            await self.command_handler.handle_butt(ctx)

    @commands.command(name="дрын")
    async def club(self, ctx: commands.Context) -> None:
        """Handle the club command."""
        if self.active:
            await self.command_handler.handle_club(ctx)

    @commands.command(name="я")
    async def me(self, ctx: commands.Context) -> None:
        """Handle the me command to show user stats."""
        if self.active:
            await self.command_handler.handle_me(ctx)

    @commands.command(name="топ")
    async def leaders(self, ctx: commands.Context) -> None:
        """Handle the leaders command to show top users."""
        if self.active:
            await self.command_handler.handle_leaders(ctx)

    @commands.command(name="voteban")
    async def voteban(self, ctx: commands.Context) -> None:
        """Handle the voteban command."""
        if self.active:
            await self.command_handler.handle_voteban(ctx)

    @commands.command(name="очко")
    async def twenty_one(self, ctx: commands.Context) -> None:
        """Handle the twenty_one command for users with free tickets."""
        if not self.active:
            return

        now = time.time()
        if now - self.command_handler.twenty_one_last_called < self.command_handler.twenty_one_global_cooldown:
            return

        self.command_handler.twenty_one_last_called = now

        twitch_id = str(ctx.author.id)
        username = str(ctx.author.name)

        if not await self.command_handler.twenty_one_game.has_tickets(twitch_id):
            await ctx.send(f'{username}, у тебя нет билетов для игры! Пройди "Испытание пивом" agabeer')
            return

        await self.command_handler.handle_twenty_one(ctx)
        await self.command_handler.twenty_one_game.consume_ticket(twitch_id)

    @commands.command(name="ботзаткнись")
    async def bot_sleep(self, ctx: commands.Context) -> None:
        """Deactivate the bot (admin only)."""
        if not is_admin(self, ctx.author.name):
            return
        self.active = False
        self.manual_override = False
        self.scheduled_offline = False
        await ctx.send("banka Алибидерчи! Бот выключен.")

    @commands.command(name="ботговори")
    async def bot_wake(self, ctx: commands.Context) -> None:
        """Activate the bot (admin only)."""
        if not is_admin(self, ctx.author.name):
            return
        self.manual_override = True
        self.scheduled_offline = False
        self.active = True
        await ctx.send("deshovka Бот снова активен!")

    async def scheduled_activity_controller(self) -> None:
        """
        Manage the bot's activity according to a schedule.

        This coroutine runs continuously and checks whether the current time
        falls within the configured offline window. It will automatically
        deactivate the bot and send an offline message if necessary. It also
        persists the last shutdown in the database to avoid sending repeated
        messages on bot restarts.

        The offline window can be overridden manually by an admin using commands.
        """
        import asyncio
        from datetime import datetime
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

        while True:
            if not self.is_connected:
                await asyncio.sleep(5)
                continue

            schedule = self.config.get("schedule", {})
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

            record = await self.db.get_scheduled_offline(today) if self.db else None
            message_already_sent = record.sent_message if record else False

            if not self.manual_override and in_offline_window(now_time, off_time, on_time):
                if not self.scheduled_offline:
                    self.active = False
                    self.scheduled_offline = True

                if not message_already_sent:
                    for channel in self.connected_channels:
                        await channel.send(
                            "Bedge отключаюсь на время киношного. "
                            "Разбудить: !ботговори Заткнуть: !ботзаткнись (admin only)"
                        )
                    if self.db:
                        await self.db.set_scheduled_offline(today, sent_message=True)

            else:
                if self.scheduled_offline or message_already_sent:
                    self.scheduled_offline = False
                    self.manual_override = False

                    if not self.active:
                        self.active = True
                        for channel in self.connected_channels:
                            await channel.send("peepoArrive работаем")

                    if self.db:
                        await self.db.set_scheduled_offline(today, sent_message=False)

            await asyncio.sleep(60)

    async def close(self) -> None:
        """Clean up resources and close the bot gracefully."""
        logger.info("Shutdown...")
        self.is_connected = False

        with suppress(Exception):
            await self.eventsub.close()

        with suppress(Exception):
            await self.api.close()

        if self.db:
            with suppress(Exception):
                await self.db.close()

        with suppress(Exception):
            await super().close()

        logger.info("TwitchBot closed")
