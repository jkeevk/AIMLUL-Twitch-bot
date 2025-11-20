import logging
import time
from typing import Any

from src.commands.managers.cache_manager import CacheManager
from src.commands.managers.user_manager import UserManager
from src.commands.games.collectors_game import CollectorsGame
from src.commands.games.twenty_one import TwentyOneGame
from src.commands.games.simple_commands import SimpleCommandsGame


class CommandHandler:
    """
    Main command handler class that coordinates all game commands and interactions.

    Responsible for routing commands to appropriate game handlers and managing
    shared resources.
    """

    def __init__(self, bot: Any) -> None:
        """
        Initialize CommandHandler with bot instance and all game handlers.

        Args:
            bot: Main bot instance providing API and database access
        """
        self.bot = bot
        self.api = bot.api
        self.db = bot.db
        self.logger = logging.getLogger(__name__)

        self.cache_manager = CacheManager()
        self.user_manager = UserManager(bot, self.cache_manager)

        self.collectors_game = CollectorsGame(self)
        self.twenty_one_game = TwentyOneGame(self)
        self.simple_commands_game = SimpleCommandsGame(self)

    def get_current_time(self) -> float:
        """
        Get current timestamp for consistent time operations.

        Returns:
            Current time as float timestamp
        """
        return time.time()

    async def handle_gnome(self, message: Any) -> None:
        """Handle gnome collector trigger in chat messages."""
        await self.collectors_game.handle_gnome(message)

    async def handle_applecat(self, message: Any) -> None:
        """Handle applecat collector trigger in chat messages."""
        await self.collectors_game.handle_applecat(message)

    async def handle_club(self, ctx: Any) -> None:
        """Handle club command."""
        await self.simple_commands_game.handle_club_command(ctx)

    async def handle_butt(self, ctx: Any) -> None:
        """Handle butt command."""
        await self.simple_commands_game.handle_butt_command(ctx)

    async def handle_barrel(self, ctx: Any) -> None:
        """Handle test barrel command (admin functionality)."""
        await self.simple_commands_game.handle_test_barrel_command(ctx)

    async def handle_twenty_one(self, ctx: Any) -> None:
        """Handle main twenty-one game command."""
        await self.twenty_one_game.handle_command(ctx)

    async def handle_me(self, ctx: Any) -> None:
        """Handle player statistics command."""
        await self.twenty_one_game.handle_me_command(ctx)

    async def handle_leaders(self, ctx: Any) -> None:
        """Handle leaderboard display command."""
        await self.twenty_one_game.handle_leaders_command(ctx)

    async def close(self) -> None:
        """Clean up resources on shutdown."""
        try:
            self.logger.info("Closing CommandHandler resources...")
            await self.api.close()
            self.logger.info("CommandHandler resources closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing CommandHandler: {e}")
