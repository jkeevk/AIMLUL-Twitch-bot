import logging
import time

from src.commands.managers.cache_manager import CacheManager
from src.commands.managers.user_manager import UserManager
from src.commands.games.collectors_game import CollectorsGame
from src.commands.games.twenty_one import TwentyOneGame
from src.commands.games.simple_commands import SimpleCommandsGame


class CommandHandler:
    def __init__(self, bot):
        self.bot = bot
        self.api = bot.api
        self.db = bot.db
        self.logger = logging.getLogger(__name__)

        # Инициализация менеджеров
        self.cache_manager = CacheManager()
        self.user_manager = UserManager(bot, self.cache_manager)

        # Инициализация игр
        self.collectors_game = CollectorsGame(self)
        self.twenty_one_game = TwentyOneGame(self)
        self.simple_commands_game = SimpleCommandsGame(self)

    def get_current_time(self) -> float:
        """Возвращает текущее время (для единообразия)"""
        return time.time()

    # Методы для коллекторов (обработка сообщений)
    async def handle_gnome(self, message) -> None:
        await self.collectors_game.handle_gnome(message)

    async def handle_applecat(self, message) -> None:
        await self.collectors_game.handle_applecat(message)

    # Методы для простых команд
    async def handle_club(self, ctx) -> None:
        await self.simple_commands_game.handle_club_command(ctx)

    async def handle_butt(self, ctx) -> None:
        await self.simple_commands_game.handle_butt_command(ctx)

    async def handle_test_barrel(self, ctx) -> None:
        await self.simple_commands_game.handle_test_barrel_command(ctx)

    # Методы для игры в 21
    async def handle_twenty_one(self, ctx) -> None:
        await self.twenty_one_game.handle_command(ctx)

    async def handle_me(self, ctx) -> None:
        await self.twenty_one_game.handle_me_command(ctx)

    async def handle_leaders(self, ctx) -> None:
        await self.twenty_one_game.handle_leaders_command(ctx)

    async def close(self):
        """Закрывает ресурсы при завершении"""
        try:
            self.logger.info("🔌 Закрываю ресурсы CommandHandler...")
            await self.api.close()
            self.logger.info("✅ Ресурсы CommandHandler закрыты")
        except Exception as e:
            self.logger.error(f"🚨 Ошибка при закрытии CommandHandler: {e}")