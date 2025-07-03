import asyncio
import logging
import os
import sys

from twitchio.ext import commands

from src.commands.command_handler import CommandHandler
from src.core.config_loader import load_settings
from src.utils.token_manager import TokenManager
from src.db.database import Database

CONFIG_PATH = "/app/settings.ini"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class TwitchBot(commands.Bot):
    def __init__(self):
        """Инициализация бота"""
        self.config = load_settings(CONFIG_PATH)
        self.logger = logging.getLogger(__name__)
        self.token_manager = TokenManager(CONFIG_PATH)

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
        self.shutdown_requested = False

    async def update_token(self, new_token: str):
        self._http.token = new_token
        self.logger.info("🆙 Токен бота успешно обновлён в HTTP-клиенте!")

        if hasattr(self, "_connection") and self._connection is not None:
            try:
                await self._connection.send(f"PASS oauth:{new_token}\r\n")
                await self._connection.send(f"NICK {self.nick}\r\n")
                for cap in self._connection.modes:
                    await self._connection.send(f"CAP REQ :twitch.tv/{cap}")
                self.logger.info("✅ Учетные данные в IRC обновлены")
            except Exception as e:
                self.logger.error(f"🚨 Ошибка обновления IRC: {e}")

        if hasattr(self, "command_handler") and hasattr(self.command_handler, "api"):
            await self.command_handler.api.refresh_headers()
            self.logger.info("🔄 Заголовки TwitchAPI обновлены после смены токена")
        else:
            self.logger.warning("⚠️ API хендлер недоступен для обновления заголовков")

    async def event_ready(self):
        """Обработчик готовности бота"""
        self.logger.info(f"🔑 Logged in as | {self.nick}")
        self.logger.info(f"🌐 Connected to: {self.connected_channels}")
        self.logger.info(f"🆔 User ID: {self.user_id}")
        self.logger.info("🤖 Bot is running")

        self.logger.info("🔄 Обновляю токен при запуске...")
        new_token = await self.token_manager.refresh_access_token()
        await self.update_token(new_token)

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
            "applecatgun": self.command_handler.handle_applecat,
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
    async def zhopa_command(self, ctx):
        """Обработка команды !жопа со случайным эффектом"""
        await self.command_handler.handle_zhopa(ctx)

    @commands.command(name="дрын")
    async def drin_command(self, ctx):
        """Обработка команды !дрын с таймаутом"""
        await self.command_handler.handle_drin(ctx)

    @commands.command(name="очко")
    async def ochko_command(self, ctx):
        """Обработка команды !очко"""
        await self.command_handler.handle_ochko(ctx)

    @commands.command(name="я")
    async def me_command(self, ctx):
        """Обработка команды !я"""
        await self.command_handler.handle_me(ctx)

    @commands.command(name="топ")
    async def leaders_command(self, ctx):
        """Обработка команды !топ"""
        await self.command_handler.handle_leaders(ctx)

    @commands.command(name="ботзаткнись")
    async def shutdown_command(self, ctx):
        """
        Команда для выключения бота (только для администраторов)
        """
        if ctx.author.name.lower() not in self.config.get("admins", []):
            self.logger.warning(
                f"Попытка выключения от неавторизованного пользователя: {ctx.author.name}"
            )
            return

        self.logger.warning(
            f"🛑 Запрос на выключение от администратора: {ctx.author.name}"
        )
        await ctx.send("Алибидерчи, лошки! GAGAGA Выключаюсь...")

        self.shutdown_requested = True

        asyncio.create_task(self.shutdown_sequence())

    async def shutdown_sequence(self):
        self.logger.info("🚦 Начинаю процедуру выключения...")
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        await self.close()
        self.logger.info("🛑 Цикл событий остановлен")

    async def periodic_token_refresh(self):
        """Периодическое обновление токена"""
        self.logger.info("⏳ Запущена задача периодического обновления токена")
        while True:
            try:
                await asyncio.sleep(self.config["refresh_token_delay_time"])

                if self.shutdown_requested:
                    self.logger.info("🛑 Обновление токена прервано из-за выключения")
                    return

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
        if self._closing:
            return
        self._closing = True
        self.logger.info("🛑 Начало процесса остановки бота...")

        if self.token_refresh_task:
            self.token_refresh_task.cancel()
            try:
                await self.token_refresh_task
            except asyncio.CancelledError:
                pass

        if hasattr(self, "_http") and self._http:
            await self._http.close()
        await super().close()

        if self.db:
            await self.db.close()

        self.logger.info("🔌 Все соединения закрыты")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    bot = TwitchBot()
    try:
        bot.run()
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}", exc_info=True)
    finally:
        logging.info("Приложение завершено")
