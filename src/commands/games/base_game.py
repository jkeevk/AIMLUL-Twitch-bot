import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twitchio.ext.commands import Context

    from src.commands.command_handler import CommandHandler


class BaseGame(ABC):
    """
    Abstract base class for all game implementations.

    Provides common functionality for command handling, cooldown management,
    and access to shared resources through the command handler.
    """

    def __init__(self, command_handler: "CommandHandler") -> None:
        self.command_handler = command_handler
        self.bot = command_handler.bot
        self.api = command_handler.api
        self.db = command_handler.db
        self.cache_manager = command_handler.cache_manager
        self.user_manager = command_handler.user_manager
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    async def handle_command(self, ctx: "Context") -> None:
        """
        Process game command.

        Args:
            ctx: Command context object

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement handle_command method")

    def check_cooldown(self, command_name: str) -> bool:
        """
        Check if command is ready to execute based on cooldown.

        Args:
            command_name: Name of the command to check

        Returns:
            True if command can be executed, False if still on cooldown
        """
        current_time = self.command_handler.get_current_time()
        last_time = self.cache_manager.command_cooldowns.get(command_name, 0)
        delay_time = self.bot.config.get("command_delay_time", 45)

        time_since_last = current_time - last_time
        can_execute = time_since_last >= delay_time

        if not isinstance(can_execute, bool):
            return False

        return can_execute

    def update_cooldown(self, command_name: str) -> None:
        """
        Update command cooldown timestamp.

        Args:
            command_name: Name of the command to update
        """
        current_time = self.command_handler.get_current_time()
        self.cache_manager.command_cooldowns[command_name] = int(current_time)
