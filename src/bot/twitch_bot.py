import logging
import os
import time
from contextlib import suppress
from typing import Any

from redis.asyncio import Redis
from twitchio import Message
from twitchio.ext import commands

from src.api.twitch_api import TwitchAPI
from src.bot.commands_config import COMMANDS
from src.commands.command_handler import CommandHandler
from src.commands.managers.cache_manager import CacheManager
from src.commands.permissions import is_admin
from src.commands.triggers.text_triggers import build_triggers
from src.core.config_loader import load_settings
from src.db.database import Database
from src.eventsub.handlers import handle_eventsub_reward
from src.eventsub.manager import EventSubManager
from src.utils.token_manager import TokenManager

logger = logging.getLogger(__name__)


class TwitchBot(commands.Bot):  # type: ignore[misc]
    """Manage Twitch chat, commands, and EventSub integrations."""

    config: dict[str, Any]
    token_manager: TokenManager
    active: bool
    api: TwitchAPI
    db: Database | None
    command_handler: CommandHandler
    eventsub: EventSubManager
    triggers: dict[str, Any]
    is_connected: bool

    def __init__(self, token_manager: TokenManager, bot_token: str, redis: Redis) -> None:
        """
        Initialize the Twitch bot with commands, EventSub, and database integration.

        Args:
            token_manager: Token manager for handling OAuth tokens.
            bot_token: Authentication token for the bot.
            redis: Redis connection for caching and state tracking.
        """
        self.config = load_settings()
        self.token_manager = token_manager
        self.active = True
        self.is_connected = False
        self.redis = redis

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
        self.cache_manager = CacheManager(self.redis)
        self.command_handler = CommandHandler(self)
        self.eventsub = EventSubManager(self)
        self.triggers = build_triggers(self)

    async def event_token_expired(self) -> str | None:
        """
        Handle EventSub token expiration.

        Refresh and return a new STREAMER token for EventSub.

        Returns:
            A valid STREAMER token if refreshed successfully, otherwise None.
        """
        try:
            token = await self.token_manager.get_streamer_token()
            logger.info("Streamer token for EventSub updated")
            return token
        except Exception as e:
            logger.error(f"Failed to refresh streamer token for EventSub: {e}")
            return None

    async def event_ready(self) -> None:
        """
        Handle bot readiness event.

        Connect to database, setup EventSub, and verify Redis connection.
        """
        self.is_connected = True

        if self.db:
            try:
                await self.db.connect()
            except Exception as e:
                logger.error("DB connection failed", exc_info=e)
                self.db = None

        await self.eventsub.setup()

        if self.redis:
            try:
                await self.redis.ping()
                logger.info("Redis OK")
            except Exception as e:
                logger.error("Redis ping failed", exc_info=e)
        logger.info("Bot ready")

    async def event_message(self, message: Message) -> None:
        """
        Handle incoming chat messages.

        Mark users as active, trigger keyword handlers, and process commands.

        Args:
            message: Incoming Twitch chat message object.
        """
        if message.echo:
            return
        if message.author:
            await self.cache_manager.mark_user_active(
                message.channel.name,
                message.author.name,
                message.author.id,
            )
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

    async def event_disconnect(self) -> None:
        """Handle bot disconnection from Twitch and update connection state."""
        logger.warning("Bot disconnected from Twitch")
        self.is_connected = False

    @commands.command(name=COMMANDS["butt"])
    async def butt(self, ctx: commands.Context) -> None:
        """Handle the 'butt' command and invoke command handler."""
        if self.active:
            await self.command_handler.handle_butt(ctx)

    @commands.command(name=COMMANDS["club"])
    async def club(self, ctx: commands.Context) -> None:
        """Handle the 'club' command and invoke command handler."""
        if self.active:
            await self.command_handler.handle_club(ctx)

    @commands.command(name=COMMANDS["me"])
    async def me(self, ctx: commands.Context) -> None:
        """Handle the 'me' command and show user statistics."""
        if self.active:
            await self.command_handler.handle_me(ctx)

    @commands.command(name=COMMANDS["leaders"])
    async def leaders(self, ctx: commands.Context) -> None:
        """Handle the 'leaders' command and show top users."""
        if self.active:
            await self.command_handler.handle_leaders(ctx)

    @commands.command(name=COMMANDS["voteban"])
    async def voteban(self, ctx: commands.Context) -> None:
        """Handle the 'voteban' command and invoke command handler."""
        if self.active:
            await self.command_handler.handle_voteban(ctx)

    @commands.command(name=COMMANDS["twenty_one"])
    async def twenty_one(self, ctx: commands.Context) -> None:
        """
        Handle the 'twenty_one' command for users with free tickets.

        Check ticket availability, enforce global cooldown, and consume a ticket.
        """
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

    @commands.command(name=COMMANDS["bot_sleep"])
    async def bot_sleep(self, ctx: commands.Context) -> None:
        """Deactivate the bot (admin only) and reset override states."""
        if not is_admin(self, ctx.author.name):
            return
        if hasattr(self, "manager"):
            await self.manager.set_bot_sleep()

    @commands.command(name=COMMANDS["bot_wake"])
    async def bot_wake(self, ctx: commands.Context) -> None:
        """Activate the bot (admin only) and cancel today's override."""
        if not is_admin(self, ctx.author.name):
            return
        if hasattr(self, "manager"):
            await self.manager.set_bot_wake()

    async def close(self) -> None:
        """Clean up resources and close the bot, including EventSub, API, and database."""
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
