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
    Coordinate game commands and interactions for the Twitch bot.

    Routes commands to the appropriate game handlers and manages shared resources
    such as API, database, and cached data.
    """

    def __init__(self, bot: Any) -> None:
        """
        Initialize the CommandHandler with the bot and game handlers.

        Args:
            bot: The main bot instance providing access to API, database, and cache.
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
        Get the current timestamp.

        Returns:
            Current time as a float timestamp.
        """
        return time.time()

    async def handle_gnome(self, message: Any) -> None:
        """
        Handle the 'gnome' collector trigger.

        Args:
            message: The incoming Twitch message object.
        """
        await self.collectors_game.handle_gnome(message)

    async def handle_applecat(self, message: Any) -> None:
        """
        Handle the 'applecat' collector trigger.

        Args:
            message: The incoming Twitch message object.
        """
        await self.collectors_game.handle_applecat(message)

    async def handle_club(self, ctx: Any) -> None:
        """
        Handle the 'club' command.

        Args:
            ctx: The command context.
        """
        await self.simple_commands_game.handle_club_command(ctx)

    async def handle_butt(self, ctx: Any) -> None:
        """
        Handle the 'butt' command.

        Args:
            ctx: The command context.
        """
        await self.simple_commands_game.handle_butt_command(ctx)

    async def handle_trash_barrel(self, user_name: str, channel_name: str) -> None:
        """
        Handle the 'trash barrel' command.

        Args:
            user_name: Twitch username of the player.
            channel_name: Channel where the command was issued.
        """
        await self.beer_barrel_game.handle_trash_command(user_name, channel_name)

    async def handle_kaban_barrel(self, user_name: str, channel_name: str) -> None:
        """
        Handle the 'kaban barrel' command.

        Args:
            user_name: Twitch username of the player.
            channel_name: Channel where the command was issued.
        """
        await self.beer_barrel_game.handle_kaban_command(user_name, channel_name)

    async def handle_beer_barrel(self, user_name: str, channel_name: str) -> None:
        """
        Handle the 'beer barrel' command.

        Args:
            user_name: Twitch username of the player.
            channel_name: Channel where the command was issued.
        """
        await self.beer_barrel_game.handle_beer_barrel_command(user_name, channel_name)

    async def handle_beer_challenge(self, user_id: str, user_name: str, user_input: str, channel_name: str) -> None:
        """
        Handle the 'beer challenge' command.

        Args:
            user_id: Twitch user ID of the player.
            user_name: Twitch username of the player.
            user_input: User-provided input for the challenge.
            channel_name: Channel where the command was issued.
        """
        await self.beer_challenge_game.handle_beer_challenge_command(user_id, user_name, user_input, channel_name)

    async def handle_twenty_one(self, ctx: Any) -> None:
        """
        Handle the 'twenty-one' game command.

        Args:
            ctx: The command context.
        """
        await self.twenty_one_game.handle_command(ctx)

    async def handle_me(self, ctx: Any) -> None:
        """
        Handle the player statistics command.

        Args:
            ctx: The command context.
        """
        await self.twenty_one_game.handle_me_command(ctx)

    async def handle_leaders(self, ctx: Any) -> None:
        """
        Handle the leaderboard display command.

        Args:
            ctx: The command context.
        """
        await self.twenty_one_game.handle_leaders_command(ctx)

    async def handle_voteban(self, ctx: Any) -> None:
        """
        Handle the voteban command.

        Args:
            ctx: The command context.
        """
        await self.simple_commands_game.handle_voteban_command(ctx)

    async def close(self) -> None:
        """
        Clean up resources on shutdown.

        Closes API connections and logs shutdown status.
        """
        try:
            self.logger.info("Closing CommandHandler resources...")
            await self.api.close()
            self.logger.info("CommandHandler resources closed successfully")
        except Exception as e:
            self.logger.error(f"Error closing CommandHandler: {e}")
