import asyncio
import random
from src.commands.models.chatters import ChatterData
from typing import Optional

from twitchio.ext.commands import Context
from src.commands.games.base_game import BaseGame

MAX_MESSAGE_LENGTH = 255

class BeerBarrelGame(BaseGame):
    """Handles the Beer Barrel reward without requiring a chat context."""

    async def handle_beer_barrel_command(self, user_name: str, channel_name: str) -> None:
        """
        Handle the Beer Barrel reward command for any user.

        Args:
            user_name: Name of the user who triggered the reward.
            channel_name: Name of the channel where the reward was triggered.
        """
        try:
            if self.cache_manager.should_update_cache() or len(self.cache_manager.get_cached_chatters()) < 50:
                chatters = await self.api.get_chatters(channel_name)
                normalized: list[ChatterData] = [
                    ChatterData(
                        id=c["user_id"],
                        name=c["user_name"],
                        display_name=c["user_name"]
                    )
                    for c in chatters
                ]
                self.cache_manager._cached_chatters = self.cache_manager.filter_chatters(normalized)

            valid_chatters = self.cache_manager.get_cached_chatters()
            self.logger.info(valid_chatters)

            if not valid_chatters:
                self.logger.warning("No suitable users for barrel command")
                return

            selected_count = min(50, len(valid_chatters))
            targets = random.sample(valid_chatters, selected_count)

            async def process_timeout(target: ChatterData) -> Optional[str]:
                try:
                    if not target["id"]:
                        return None

                    status, response = await self.api.timeout_user(
                        user_id=target["id"],
                        channel_name=channel_name,
                        duration=600,
                        reason="Пивная кома",
                    )

                    if status == 200:
                        return target["name"]
                    else:
                        self.logger.warning(f"Failed to timeout {target["name"]}: status={status}")
                        return None
                except Exception as e:
                    self.logger.error(f"Error processing {target["name"]}: {e}")
                    return None

            channel = self.bot.get_channel(channel_name)
            if not channel:
                await self.bot.join_channels([channel_name])
                channel = self.bot.get_channel(channel_name)

            ascii_art_start = ("⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⠉⠀⠀⠀⠉⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡏⠀⠀⠀⠀⠀⠀⠀⠸⠉⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⡿⢿⣿⡿⠓⠀⠀⡎⠉⠉⢢⠀⠀⠀⠀⠛⢿⠋⢻⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣤⣤⣿⡀⠀⠀⠀⠓⠴⠃⣼⠀⠀⠀⠀⠀⢸⣿⠁⣸⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⠀⢹⣿⠒⠒⠒⠒⠒⠚⢿⠀⣤⣄⠀⢸⣛⣛⠛⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣶⠛⣿⡄⠀⣀⠀⠀⣀⣼⠀⣧⡈⠷⢾⣿⣿⡇⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⡏⠀⠀⡏⢿⣀⣿⠁⠀⢸⣿⣿⡇⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⡇⠀⠀⡇⠀⠉⣿⠀⠀⢸⣿⣿⡇⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⡇⠀⠀⡇⠀⠀⣿⠀⠀⢸⣋⣉⣁⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⡇⠀⠀⡇⠀⠀⣿⠀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⡇⠀⠀⡇⠀⠀⣿⠀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⣇⠀⠀⣧⠀⠀⣿⡀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣇⠀⠁⠀⠀⠈⠀⠀⠈⠀⢀⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿")
            await channel.send(ascii_art_start)
            await channel.send(f"catLicks ПРИГОТОВИЛИСЬ! ДО ВСКРЫТИЯ ПИВНОЙ КЕГИ 30 СЕКУНД! catLicks")
            await asyncio.sleep(60)
            await channel.send(f"catLicks ГОТОВЬТЕ КРУЖКИ! 10 СЕКУНД catLicks")
            await asyncio.sleep(10)
            await channel.send(f"Кто тащил кегу??? Wigglecat Прячься, сейчас пизданёт KabanRunZaPivom")
            await asyncio.sleep(2)
            ascii_art_end = ("⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠟⠛⠛⠋⠋⠙⠻⠛⠿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⠟⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠹⢿⣿⣿⣿⣿⣿⣿ ⣿⣿⠿⠛⠁⠀⠀⠀⠀⢀⣠⣠⠄⢀⣄⣀⠀⣤⣴⣆⠀⠀⠀⣼⣿⣿⣿⣿⣿⣿ ⠟⠋⢀⠀⢠⡗⠂⠀⠀⢂⠎⣠⠶⢿⣿⣿⣿⣿⣿⣿⣷⣾⣿⣿⣿⣿⣿⣿⣿⣿ ⠀⢠⣦⠿⠛⠀⠀⡄⠀⠈⠀⠉⠀⠘⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⠀⠀⠉⠀⠀⠀⠀⠁⠀⠀⠀⢀⣠⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠈⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠙⠿⢿⣿⣿⣿⣿⣿⣿⣿⣿⠿⠋ ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⣀⣉⣩⣩⣄⣀⣠⣤⣤ ⠀⠀⠀⠀⠀⠀⢠⣼⣦⣦⣄⠀⠀⠰⢦⣤⣤⣀⣀⣀⣀⣀⣀⣚⣛⣛⣻⣻⣿⣿")
            await asyncio.sleep(2)
            await channel.send(ascii_art_end)

            punished_users = []

            batch_size = 5
            for i in range(0, len(targets), batch_size):
                batch = targets[i:i + batch_size]
                tasks = [process_timeout(target) for target in batch]
                results = await asyncio.gather(*tasks)
                for result in results:
                    if result:
                        punished_users.append(result)
                if i + batch_size < len(targets):
                    await asyncio.sleep(0.5)

            if punished_users:
                prefix = f"@{user_name} напоил пивасом. В алкокому впали: "
                current_message = prefix
                for name in punished_users:
                    mention = f"@{name}, "
                    if len(current_message) + len(mention) > MAX_MESSAGE_LENGTH:
                        await channel.send(current_message.rstrip(", "))
                        current_message = mention
                    else:
                        current_message += mention
                if current_message.strip():
                    await channel.send(current_message.rstrip(", "))
            else:
                await channel.send(f"@{user_name} кодер мудак. Бочка дала осечку! @FleshDota, разберись")
            await asyncio.sleep(1)
            await channel.send("raveCat Здоровья подпивасам raveCat")

            self.logger.info(f"Test barrel completed. Successful: {len(punished_users)}")

        except Exception as e:
            self.logger.error(f"Critical error in test barrel: {e}")

    async def handle_command(self, ctx: Context) -> None:
        """Not used for simple commands."""
        pass
