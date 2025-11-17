import time
from typing import Dict

from src.commands.games.base_game import BaseGame
from src.commands.models.game_models import BaseCollector, CollectorConfig
from src.utils.helpers import is_privileged


class CollectorsGame(BaseGame):
    """Игра с коллекторами (гном, applecat)"""

    def __init__(self, command_handler):
        super().__init__(command_handler)

        # Создаем коллекторы
        self.collectors: Dict[str, BaseCollector] = {
            "gnome": BaseCollector(CollectorConfig(
                name="gnome",
                reset_time=300,
                reason="гном",
                timeout_message="@{target_name}, попался гном Angry 👉🚪",
                duration=60,
                required_participants=3
            )),
            "applecatpanik": BaseCollector(CollectorConfig(
                name="applecatpanik",
                reset_time=300,
                reason="не бегать",
                timeout_message="@{target_name}, не бегать! Applecatrunt",
                duration=60,
                required_participants=3
            ))
        }

    async def handle_gnome(self, message) -> None:
        """Обрабатывает сообщение GNOME"""
        await self._handle_collector(message, "gnome")

    async def handle_applecat(self, message) -> None:
        """Обрабатывает сообщение applecatPanik"""
        await self._handle_collector(message, "applecatpanik")

    async def _handle_collector(self, message, collector_type: str) -> None:
        """Обработчик для команд со сбором участников"""
        try:
            if is_privileged(message.author):
                return

            # Защита от спама
            if not self.cache_manager.can_user_participate(message.author.id):
                return

            self.cache_manager.update_user_cooldown(message.author.id)
            collector = self.collectors[collector_type]

            # Автосброс при долгом бездействии
            if collector.should_reset() and collector.participants:
                self.logger.info(f"🔄 Автосброс сборщика {collector_type}")
                collector.reset()

            # Добавление участника
            if not collector.add(message.author.id, message.author.name):
                return

            self.logger.info(
                f"➕ {message.author.name} добавлен в {collector_type}. Всего: {len(collector.participants)}"
            )

            # Проверка заполненности
            if not collector.is_full():
                return

            # Берем случайного участника
            target_id, target_name = collector.get_random()
            self.logger.info(
                f"🔨 Попытка таймаута {target_name} ({target_id}) из сбора {collector_type}"
            )

            status, response = await self.api.timeout_user(
                user_id=target_id,
                channel_name=message.channel.name,
                duration=collector.config.duration,
                reason=collector.config.reason,
            )

            if status == 200:
                await message.channel.send(
                    collector.config.timeout_message.format(target_name=target_name)
                )
            elif status == 401:
                self.logger.error("❌ Неавторизован - требуется обновление токена")
            elif status == 429:
                self.logger.warning("⚠️ Слишком много запросов - снизьте частоту")
            else:
                self.logger.error(f"🚨 Ошибка API: {status} - {response}")

            # Сбрасываем сборщик
            collector.reset()

        except Exception as e:
            self.logger.error(f"🚨 Ошибка обработки {collector_type}: {e}")

    async def handle_command(self, ctx) -> None:
        """Не используется для коллекторов (они обрабатываются через сообщения)"""
        pass