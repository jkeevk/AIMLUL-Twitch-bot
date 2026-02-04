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
        self.logger = logging.getLogger(__name__)
        self.cache_manager = self.bot.cache_manager

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

    async def check_cooldown(self, command_name: str) -> bool:
        """
        Check if command is ready to execute based on cooldown.

        Args:
            command_name: Name of the command to check

        Returns:
            True if command can be executed, False if still on cooldown
        """
        result = await self.bot.cache_manager.get_command_cooldown(command_name)
        return bool(result)

    async def update_cooldown(self, command_name: str, delay_time: int | None = None) -> None:
        """
        Update command cooldown timestamp.

        Args:
            command_name: Name of the command to update
            delay_time: Optional cooldown duration in seconds (defaults to bot config)
        """
        if delay_time is None:
            delay_time = self.bot.config.get("command_delay_time", 45)
        await self.bot.cache_manager.set_command_cooldown(command_name, delay_time)
