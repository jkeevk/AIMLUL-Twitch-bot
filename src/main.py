import asyncio
import logging
import sys
import os
from contextlib import suppress
from typing import Dict, Any, Optional

from twitchio.ext import commands

from src.utils.token_manager import TokenManager
from src.api.twitch_api import TwitchAPI
from src.core.config_loader import load_settings
from src.commands.command_handler import CommandHandler
from src.db.database import Database

CONFIG_PATH = "/app/settings.ini"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("bot")


class TwitchBot(commands.Bot):
    """Twitch bot implementation handling chat commands and automated responses."""

    def __init__(self, token_manager: TokenManager) -> None:
        """
        Initialize the Twitch bot.

        Args:
            token_manager: Manager for handling authentication tokens
        """
        self.config = load_settings(CONFIG_PATH)
        self.token_manager = token_manager
        self.active = True
        self._refresh_task_started = False

        super().__init__(
            token=self.token_manager.token,
            client_id=self.token_manager.client_id,
            client_secret=self.token_manager.client_secret,
            prefix="!",
            initial_channels=self.config["channels"],
        )

        self.api = TwitchAPI(self)

        dsn = os.getenv("DATABASE_URL") or self.config["database"].get("dsn")
        self.db = Database(dsn) if dsn else None
        self.command_handler = CommandHandler(self)
        self.token_refresh_task: Optional[asyncio.Task] = None

    async def update_token(self, token: str) -> None:
        """Update authentication token and trigger WebSocket reconnection."""
        self._http.token = token
        await self.api.refresh_headers()
        logger.info("Token updated successfully")

    async def periodic_refresh(self) -> None:
        """Periodically refresh authentication token."""
        delay = self.config["refresh_token_delay_time"]
        logger.info("Starting scheduled token refresh")

        while True:
            try:
                await asyncio.sleep(delay)
                logger.info("Refreshing authentication token...")
                new_token = await self.token_manager.refresh_access_token()
                await self.update_token(new_token)
            except Exception as e:
                logger.error(f"Token refresh failed: {e}")
                await asyncio.sleep(60)

    async def event_ready(self) -> None:
        """Handle bot ready event."""
        logger.info(f"Bot logged in as {self.nick}")

        if self.db:
            try:
                await self.db.connect()
                logger.info("Database connection established")
            except Exception as e:
                logger.error(f"Database connection failed: {e}")
                self.db = None

        if not self._refresh_task_started:
            self._refresh_task_started = True
            self.token_refresh_task = asyncio.create_task(self.periodic_refresh())

    async def event_message(self, message) -> None:
        """Handle incoming chat messages."""
        if message.echo:
            return

        text = message.content.lower()
        triggers = {
            "gnome": self.command_handler.handle_gnome,
            "applecatpanik": self.command_handler.handle_applecat,
        }

        for word, handler in triggers.items():
            if word in text:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(f"Trigger handler error for '{word}': {e}", exc_info=True)
                return

        await self.handle_commands(message)
        logger.info(f"{message.author.name}: {message.content}")

    @commands.command(name="жопа")
    async def butt(self, ctx) -> None:
        """Handle butt command."""
        if self.active:
            await self.command_handler.handle_butt(ctx)

    @commands.command(name="дрын")
    async def club(self, ctx) -> None:
        """Handle club command."""
        if self.active:
            await self.command_handler.handle_club(ctx)

    @commands.command(name="бочка")
    async def test_barrel(self, ctx) -> None:
        """Handle test barrel command (admin only)."""
        if ctx.author.name.lower() not in self.config.get("admins", []):
            logger.warning(f"Unauthorized test_barrel attempt by {ctx.author.name}")
            return
        await self.command_handler.handle_barrel(ctx)

    @commands.command(name="очко")
    async def twentyone(self, ctx) -> None:
        """Handle twenty-one game command."""
        if self.active:
            await self.command_handler.handle_twenty_one(ctx)

    @commands.command(name="я")
    async def me(self, ctx) -> None:
        """Handle user stats command."""
        if self.active:
            await self.command_handler.handle_me(ctx)

    @commands.command(name="топ")
    async def leaders(self, ctx) -> None:
        """Handle leaderboard command."""
        if self.active:
            await self.command_handler.handle_leaders(ctx)

    @commands.command(name="ботзаткнись")
    async def bot_sleep(self, ctx) -> None:
        """Deactivate bot (admin only)."""
        if ctx.author.name.lower() not in self.config.get("admins", []):
            return
        self.active = False
        await ctx.send("banka Алибидерчи, лошки! Выключаюсь...")

    @commands.command(name="ботговори")
    async def bot_wake(self, ctx) -> None:
        """Activate bot (admin only)."""
        if ctx.author.name.lower() not in self.config.get("admins", []):
            return
        self.active = True
        await ctx.send("deshovka Бот снова в строю, очкошники! GAGAGA")

    async def close(self) -> None:
        """Clean up resources and shutdown bot gracefully."""
        logger.info("Initiating bot shutdown...")

        if self.token_refresh_task:
            self.token_refresh_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.token_refresh_task

        if self.db:
            with suppress(Exception):
                await self.db.close()

        await super().close()


async def main() -> None:
    """Main application entry point."""
    try:
        logger.info("Initializing token validation...")
        token_manager = TokenManager(CONFIG_PATH)
        await token_manager.get_access_token()

        bot = TwitchBot(token_manager)
        await bot.start()

    except Exception as e:
        logger.critical(f"Fatal startup error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
