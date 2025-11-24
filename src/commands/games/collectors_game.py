from typing import Any

from twitchio import Message
from twitchio.ext.commands import Context

from src.commands.games.base_game import BaseGame
from src.commands.models.game_models import BaseCollector, CollectorConfig
from src.commands.permissions import is_privileged


class CollectorsGame(BaseGame):
    """
    Collector-based game implementation.

    Handles games that require collecting multiple participants
    before triggering an action (gnome, applecat collectors).
    """

    def __init__(self, command_handler: Any) -> None:
        super().__init__(command_handler)

        self.collectors: dict[str, BaseCollector] = {
            "gnome": BaseCollector(
                CollectorConfig(
                    name="gnome",
                    reset_time=300,
                    reason="гном",
                    timeout_message="@{target_name}, попался гном Angry 👉🚪",
                    duration=60,
                    required_participants=3,
                )
            ),
            "applecatpanik": BaseCollector(
                CollectorConfig(
                    name="applecatpanik",
                    reset_time=300,
                    reason="не бегать",
                    timeout_message="@{target_name}, не бегать! Applecatrunt",
                    duration=60,
                    required_participants=3,
                )
            ),
        }

    async def handle_gnome(self, message: Message) -> None:
        """
        Handle GNOME collector trigger.

        Args:
            message: Incoming chat message
        """
        await self._handle_collector(message, "gnome")

    async def handle_applecat(self, message: Message) -> None:
        """
        Handle applecatPanik collector trigger.

        Args:
            message: Incoming chat message
        """
        await self._handle_collector(message, "applecatpanik")

    async def _handle_collector(self, message: Message, collector_type: str) -> None:
        """
        Process collector participation and trigger actions.

        Args:
            message: Incoming chat message
            collector_type: Type of collector to handle
        """
        try:
            if is_privileged(message.author):
                return

            if not self.cache_manager.can_user_participate(message.author.id):
                return

            self.cache_manager.update_user_cooldown(message.author.id)
            collector = self.collectors[collector_type]

            if collector.should_reset() and collector.participants:
                self.logger.info(f"Auto-reset collector {collector_type}")
                collector.reset()

            if not collector.add(message.author.id, message.author.name):
                return

            self.logger.info(f"{message.author.name} added to {collector_type}. Total: {len(collector.participants)}")

            if not collector.is_full():
                return

            random_target = collector.get_random()
            if random_target is None:
                self.logger.warning(f"{collector_type} could not select a random participant")
                return

            target_id, target_name = random_target

            self.logger.info(f"Attempting to timeout {target_name} ({target_id}) from collector {collector_type}")

            status, response = await self.api.timeout_user(
                user_id=target_id,
                channel_name=message.channel.name,
                duration=collector.config.duration,
                reason=collector.config.reason,
            )

            if status == 200:
                await message.channel.send(collector.config.timeout_message.format(target_name=target_name))
            elif status == 401:
                self.logger.error("Unauthorized - token refresh required")
            elif status == 429:
                self.logger.warning("Too many requests - slow down")
            else:
                self.logger.error(f"API error: {status} - {response}")

            collector.reset()

        except Exception as e:
            self.logger.error(f"Error handling {collector_type}: {e}")

    async def handle_command(self, ctx: Context) -> None:
        """
        Not used for collectors (handled via message triggers).

        Args:
            ctx: Command context (unused)
        """
        pass
