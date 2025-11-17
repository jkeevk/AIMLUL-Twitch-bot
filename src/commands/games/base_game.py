import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.commands.command_handler import CommandHandler


class BaseGame(ABC):
    """Базовый класс для всех игр"""

    def __init__(self, command_handler: 'CommandHandler'):
        self.command_handler = command_handler
        self.bot = command_handler.bot
        self.api = command_handler.api
        self.db = command_handler.db
        self.cache_manager = command_handler.cache_manager
        self.user_manager = command_handler.user_manager
        self.logger = logging.getLogger(__name__)

    @abstractmethod
    async def handle_command(self, ctx) -> None:
        """Обработка команды игры"""
        pass

    def check_cooldown(self, command_name: str) -> bool:
        """Проверяет кулдаун команды с логированием"""
        current_time = self.command_handler.get_current_time()
        last_time = self.cache_manager.command_cooldowns.get(command_name, 0)
        delay_time = self.bot.config.get("command_delay_time", 45)  # По умолчанию 45 секунд

        time_since_last = current_time - last_time
        can_execute = time_since_last >= delay_time

        if not can_execute:
            remaining = delay_time - time_since_last
            self.logger.info(f"⏳ Команда {command_name} на кулдауне. Осталось: {remaining:.1f}с")
        else:
            self.logger.info(f"✅ Команда {command_name} готова к выполнению")

        return can_execute

    def update_cooldown(self, command_name: str) -> None:
        """Обновляет кулдаун команды"""
        self.cache_manager.command_cooldowns[command_name] = self.command_handler.get_current_time()
        self.logger.info(f"🔄 Кулдаун команды {command_name} обновлен")