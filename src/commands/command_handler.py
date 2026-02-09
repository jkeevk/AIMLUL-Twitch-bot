import logging
import time
from typing import Any

from src.commands.games.beer_barrel import BeerBarrelGame
from src.commands.games.beer_challenge import BeerChallengeGame
from src.commands.games.collectors_game import CollectorsGame
from src.commands.games.simple_commands import SimpleCommandsGame
from src.commands.games.twenty_one import TwentyOneGame


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
        self.cache_manager = bot.cache_manager
        self.collectors_game = CollectorsGame(self)
        self.twenty_one_game = TwentyOneGame(self)
        self.simple_commands_game = SimpleCommandsGame(self)
        self.beer_barrel_game = BeerBarrelGame(self)
        self.beer_challenge_game = BeerChallengeGame(self)
        self.voteban_state: dict[str, Any] = {
            "target": None,
            "votes": set(),
            "start_time": 0.0,
        }
        self.twenty_one_global_cooldown: float = 45.0
        self.twenty_one_last_called: float = 0.0

    @staticmethod
    def get_current_time() -> float:
        """
        Get current timestamp for consistent time operations.

        Returns:
            Current time as float timestamp
        """
        return time.time()

    async def handle_gnome(self, message: Any) -> None:
        """Handle gnome collector trigger."""
        await self.collectors_game.handle_gnome(message)

    async def handle_applecat(self, message: Any) -> None:
        """Handle applecat collector trigger."""
        await self.collectors_game.handle_applecat(message)

    async def handle_club(self, ctx: Any) -> None:
        """Handle club command."""
        await self.simple_commands_game.handle_club_command(ctx)

    async def handle_butt(self, ctx: Any) -> None:
        """Handle butt command."""
        await self.simple_commands_game.handle_butt_command(ctx)

    async def handle_trash_barrel(self, user_name: str, channel_name: str) -> None:
        """Handle trash barrel command."""
        await self.beer_barrel_game.handle_trash_command(user_name, channel_name)

    async def handle_kaban_barrel(self, user_name: str, channel_name: str) -> None:
        """Handle kaban barrel command."""
        await self.beer_barrel_game.handle_kaban_command(user_name, channel_name)

    async def handle_beer_barrel(self, user_name: str, channel_name: str) -> None:
        """Handle beer barrel command."""
        await self.beer_barrel_game.handle_beer_barrel_command(user_name, channel_name)

    async def handle_beer_challenge(self, user_id: str, user_name: str, user_input: str, channel_name: str) -> None:
        """Handle beer challenge command."""
        await self.beer_challenge_game.handle_beer_challenge_command(user_id, user_name, user_input, channel_name)

    async def handle_twenty_one(self, ctx: Any) -> None:
        """Handle twenty-one game command."""
        await self.twenty_one_game.handle_command(ctx)

    async def handle_me(self, ctx: Any) -> None:
        """Handle player statistics command."""
        await self.twenty_one_game.handle_me_command(ctx)

    async def handle_leaders(self, ctx: Any) -> None:
        """Handle leaderboard display command."""
        await self.twenty_one_game.handle_leaders_command(ctx)

    async def handle_voteban(self, ctx: Any) -> None:
        """Handle voteban command."""
        await self.simple_commands_game.handle_voteban_command(ctx)

    async def close(self) -> None:
        """Clean up resources on shutdown."""
        try:
            self.logger.info("Closing CommandHandler resources...")
            await self.api.close()
            self.logger.info("CommandHandler resources closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing CommandHandler: {e}")
