import asyncio
import logging
import os
import sys

from twitchio.ext import commands

from src.commands.command_handler import CommandHandler
from src.core.config_loader import load_settings
from src.utils.token_manager import TokenManager
from src.db.database import Database
from src.api.twitch_api import TwitchAPI

CONFIG_PATH = "/app/settings.ini"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log")
    ]
)
logger = logging.getLogger(__name__)


class TwitchBot(commands.Bot):
    def __init__(self, token_manager: TokenManager):
        """Инициализация бота"""
        self.config = load_settings(CONFIG_PATH)
        self.logger = logger
        self.token_manager = token_manager
        self.active = True

        if not self.token_manager.token:
            self.logger.critical("❌ Токен отсутствует в конфигурации!")
            raise RuntimeError("Token missing in configuration")

        super().__init__(
            token=self.token_manager.token,
            client_id=self.token_manager.client_id,
            client_secret=self.token_manager.client_secret,
            prefix="!",
            initial_channels=self.config["channels"],
        )

        self.api = TwitchAPI(self)
        self.logger.info("✅ TwitchAPI инициализирован")

        dsn = os.environ.get("DATABASE_URL") or self.config["database"]["dsn"]

        if dsn:
            self.db = Database(dsn)
            self.logger.info("✅ Инициализирована база данных")
        else:
            self.logger.warning("❌ DSN для базы данных не указан")
            self.db = None

        self.command_handler = CommandHandler(self)
        self.token_refresh_task = None
        self._closing = False

    async def update_token(self, new_token: str):
        """Обновление токена во всех компонентах системы"""
        self._http.token = new_token
        self.logger.info("🆙 Токен бота успешно обновлён в HTTP-клиенте!")

        if hasattr(self, "command_handler") and hasattr(self.command_handler, "api"):
            await self.command_handler.api.refresh_headers()
            self.logger.info("🔄 Заголовки TwitchAPI обновлены")

        if hasattr(self, "_connection") and self._connection:
            self.logger.info("♻️ Переподключаю WebSocket с новым токеном...")
            await self._connection._connect()
            self.logger.info("✅ WebSocket переподключен")

    async def event_ws_close(self):
        """Обработчик обрыва соединения"""
        self.logger.warning("⚠️ WebSocket разорван! Инициирую переподключение...")

        if hasattr(self, "token_manager") and self.active:
            try:
                new_token = await self.token_manager.refresh_access_token()
                await self.update_token(new_token)
            except Exception as e:
                self.logger.error(f"🚨 Ошибка восстановления: {e}")

    async def event_ready(self):
        """Обработчик готовности бота"""
        self.logger.info(f"🔑 Logged in as | {self.nick}")
        self.logger.info(f"🌐 Connected to: {self.connected_channels}")
        self.logger.info(f"🆔 User ID: {self.user_id}")
        self.logger.info("🤖 Bot is running")

        if self.db:
            try:
                await self.db.connect()
                self.logger.info("✅ База данных подключена")
            except Exception as e:
                self.logger.error(f"❌ Ошибка подключения к БД: {e}")
                self.db = None

        self.token_refresh_task = asyncio.create_task(self.periodic_token_refresh())

    async def event_message(self, message):
        """Обработчик входящих сообщений"""
        if message.echo:
            return

        content_lower = message.content.lower()

        triggers = {
            "gnome": self.command_handler.handle_gnome,
            "applecatpanik": self.command_handler.handle_applecat,
        }
        for trigger, handler in triggers.items():
            if trigger in content_lower:
                try:
                    await handler(message)
                except Exception as e:
                    self.logger.error(
                        f"🚨 Ошибка в обработке команды: {e}", exc_info=True
                    )
                return

        await self.handle_commands(message)
        self.logger.info(f"💬 {message.author.name}: {message.content}")

    @commands.command(name="жопа")
    async def butt_command(self, ctx):
        """Обработка команды !жопа со случайным эффектом"""
        if not self.active:
            return
        await self.command_handler.handle_butt(ctx)

    @commands.command(name="дрын")
    async def club_command(self, ctx):
        """Обработка команды !дрын с таймаутом"""
        if not self.active:
            return
        await self.command_handler.handle_club(ctx)

    @commands.command(name="тестовая_бочка")
    async def test_barrel_command(self, ctx):
        """Обработка команды !тестовая_бочка с таймаутом 10 пользователей"""
        if ctx.author.name.lower() not in self.config.get("admins", []):
            self.logger.warning(
                f"Попытка бочки от неавторизованного пользователя: {ctx.author.name}"
            )
            return
        await self.command_handler.handle_test_barrel(ctx)

    @commands.command(name="очко")
    async def twenty_one_command(self, ctx):
        """Обработка команды !очко"""
        if not self.active:
            return
        await self.command_handler.handle_twenty_one(ctx)

    @commands.command(name="я")
    async def me_command(self, ctx):
        """Обработка команды !я"""
        if not self.active:
            return
        await self.command_handler.handle_me(ctx)

    @commands.command(name="топ")
    async def leaders_command(self, ctx):
        """Обработка команды !топ"""
        if not self.active:
            return
        await self.command_handler.handle_leaders(ctx)

    @commands.command(name="ботзаткнись")
    async def sleep_command(self, ctx):
        """
        Команда для отключения обработки команд (только для администраторов)
        """
        if ctx.author.name.lower() not in self.config.get("admins", []):
            self.logger.warning(
                f"Попытка отключения от неавторизованного пользователя: {ctx.author.name}"
            )
            return

        self.logger.warning(
            f"🛑 Запрос на отключение от администратора: {ctx.author.name}"
        )
        self.active = False
        await ctx.send("banka Алибидерчи, лошки! Выключаюсь...")

    @commands.command(name="ботговори")
    async def wake_command(self, ctx):
        """
        Команда для включения обработки команд (только для администраторов)
        """
        if ctx.author.name.lower() not in self.config.get("admins", []):
            self.logger.warning(
                f"Попытка активации от неавторизованного пользователя: {ctx.author.name}"
            )
            return

        self.logger.warning(
            f"🟢 Запрос на активацию от администратора: {ctx.author.name}"
        )
        self.active = True
        await ctx.send("deshovka Бот снова в строю, очкошники! GAGAGA")

    async def periodic_token_refresh(self):
        """Периодическое обновление токена"""
        self.logger.info("⏳ Запущена задача периодического обновления токена")
        while True:
            try:
                await asyncio.sleep(self.config["refresh_token_delay_time"])
                self.logger.info("🕒 Запуск планового обновления токена...")
                new_token = await self.token_manager.refresh_access_token()
                await self.update_token(new_token)
            except asyncio.CancelledError:
                self.logger.info("🛑 Задача обновления токена отменена")
                break
            except Exception as e:
                self.logger.error(f"🚨 Ошибка в обновлении токена: {e}")
                await asyncio.sleep(60)

    async def close(self):
        """Закрытие всех ресурсов (при полном выключении)"""
        if self._closing:
            return

        self._closing = True
        self.logger.info("🛑 Начало процесса остановки бота...")

        if self.token_refresh_task:
            self.token_refresh_task.cancel()
            try:
                await self.token_refresh_task
            except asyncio.CancelledError:
                self.logger.info("🛑 Задача обновления токена отменена")

        if hasattr(self, "_http") and self._http:
            await self._http.close()
            self.logger.info("🔌 HTTP-клиент закрыт")

        if self.db:
            await self.db.close()
            self.logger.info("🔌 Соединение с базой данных закрыто")

        # Закрываем CommandHandler
        if hasattr(self, "command_handler"):
            await self.command_handler.close()

        await super().close()
        self.logger.info("🔌 Все соединения закрыты")


async def main():
    """Основная асинхронная функция запуска приложения"""
    try:
        logger.info("🔄 Проверяем актуальность токена перед запуском...")
        token_manager = TokenManager(CONFIG_PATH)
        await token_manager.get_access_token()
        logger.info("✅ Токен готов к использованию")

        bot = TwitchBot(token_manager)
        logger.info("🤖 Запускаем бота...")
        await bot.start()

    except Exception as e:
        logger.critical(f"🚨 Критическая ошибка при запуске: {e}", exc_info=True)
    finally:
        logger.info("👋 Приложение завершает работу")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Приложение остановлено пользователем")
    except Exception as e:
        logger.critical(f"💀 Фатальная ошибка: {e}", exc_info=True)