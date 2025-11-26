import asyncio
import logging
import os
from contextlib import suppress
from typing import Any

from twitchio import Message
from twitchio.ext import commands

from src.api.twitch_api import TwitchAPI
from src.bot.token_refresh import periodic_refresh
from src.commands.command_handler import CommandHandler
from src.commands.permissions import is_admin
from src.commands.triggers.text_triggers import build_triggers
from src.core.config_loader import load_settings
from src.db.database import Database
from src.eventsub.handlers import handle_eventsub_reward
from src.eventsub.manager import EventSubManager
from src.utils.token_manager import TokenManager

logger = logging.getLogger(__name__)
CONFIG_PATH = "/app/settings.ini"


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
    token_refresh_task: asyncio.Task[None] | None

    def __init__(self, token_manager: TokenManager, bot_token: str) -> None:
        """
        Initialize the Twitch bot.

        Args:
            token_manager: Manager for handling token refresh operations
            bot_token: Bot authentication token
        """
        self.config = load_settings(CONFIG_PATH)
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

        if self.db:
            try:
                await self.db.connect()
            except Exception as e:
                logger.error("DB connection failed", exc_info=e)
                self.db = None

        await self.eventsub.setup()

        if not self.token_refresh_task:
            self.token_refresh_task = asyncio.create_task(periodic_refresh(self))

    async def event_message(self, message: Message) -> None:
        """
        Handle incoming chat messages.

        Args:
            message: The incoming message object
        """
        if message.echo:
            return

        text: str = message.content.lower()

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
        await handle_eventsub_reward(event, self)

    @commands.command(name="жопа")  # type: ignore[misc]
    async def butt(self, ctx: commands.Context) -> None:
        """Handle the butt command."""
        if self.active:
            await self.command_handler.handle_butt(ctx)

    @commands.command(name="дрын")  # type: ignore[misc]
    async def club(self, ctx: commands.Context) -> None:
        """Handle the club command."""
        if self.active:
            await self.command_handler.handle_club(ctx)

    @commands.command(name="бочка")  # type: ignore[misc]
    async def test_barrel(self, ctx: commands.Context) -> None:
        """Handle the test barrel command (admin only)."""
        if not is_admin(self, ctx.author.name):
            return
        await self.command_handler.handle_barrel(ctx)

    @commands.command(name="я")  # type: ignore[misc]
    async def me(self, ctx: commands.Context) -> None:
        """Handle the me command to show user stats."""
        if self.active:
            await self.command_handler.handle_me(ctx)

    @commands.command(name="топ")  # type: ignore[misc]
    async def leaders(self, ctx: commands.Context) -> None:
        """Handle the leaders command to show top users."""
        if self.active:
            await self.command_handler.handle_leaders(ctx)

    @commands.command(name="ботзаткнись")  # type: ignore[misc]
    async def bot_sleep(self, ctx: commands.Context) -> None:
        """Deactivate the bot (admin only)."""
        if not is_admin(self, ctx.author.name):
            return
        self.active = False
        await ctx.send("banka Алибидерчи! Бот выключен.")

    @commands.command(name="ботговори")  # type: ignore[misc]
    async def bot_wake(self, ctx: commands.Context) -> None:
        """Activate the bot (admin only)."""
        if not is_admin(self, ctx.author.name):
            return
        self.active = True
        await ctx.send("deshovka Бот снова активен!")

    async def close(self) -> None:
        """Clean up resources and close the bot gracefully."""
        logger.info("Shutdown...")

        if self.token_refresh_task:
            self.token_refresh_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.token_refresh_task

        if self.db:
            await self.db.close()

        await super().close()
