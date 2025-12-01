import random

from twitchio.ext.commands import Context

from src.commands.games.base_game import BaseGame
from src.commands.models.chatters import ChatterData


class BeerChallengeGame(BaseGame):
    """Handles the Beer Challenge reward without requiring a chat context."""

    async def handle_beer_challenge_command(self, user_name: str, user_input: str, channel_name: str) -> None:
        """
        Handle the Beer Challenge reward command for any user.

        Args:
            user_name: The username of the user.
            user_input: The user input (expected to be a number).
            channel_name: The channel name where the reward was redeemed.
        """
        channel = self.bot.get_channel(channel_name)
        if not channel:
            await self.bot.join_channels([channel_name])
            channel = self.bot.get_channel(channel_name)

        try:
            if not user_input.isdigit():
                await channel.send(f"@{user_name}, че пишешь то? Требуется число от 1 до 20 GAGAGA")
                self.logger.error(f"Invalid input: {user_input}")
                return

            user_obj = ChatterData(id="", name=user_name, display_name=user_name)
            amount = max(1, min(int(user_input), 20))
            success_chance = self.get_success_chance(amount)
            roll = random.randint(1, 100)

            success = roll <= success_chance

            if success:
                if amount <= 5:
                    msg = f"@{user_name}, разминочная Beerge"
                elif amount <= 10:
                    msg = f"@{user_name} выпил пивка, освежился и пошел домой PoPivu"
                elif amount <= 15:
                    msg = f"@{user_name}, куда в тебя столько влезло GIGATON"
                else:
                    msg = f"@{user_name} - не человек, зверь нахуй NixyiaSobi"

                await channel.send(msg)
                return

            fail_msgs = [
                f"@{user_name} ушел в пивную кому ystal",
                f"@{user_name} переоценил свои силы, кто убирать будет? CLEAN",
                f"@{user_name} обблевал весь пол и лежит в луже PUKERS",
                f"@{user_name} обблевал весь пол и пополз откисать на диван PUKERS",
            ]
            msg = random.choice(fail_msgs)
            await channel.send(msg)

            if not self.cache_manager.filter_chatters([user_obj]):
                self.logger.warning(f"Privileged user? {user_obj["name"]}")
                return

            target_id = await self.user_manager.get_user_id(user_name)
            if target_id:
                await self.api.timeout_user(
                    user_id=target_id, channel_name=channel_name, duration=60, reason="Испытание пивом — провал"
                )

        except Exception as e:
            self.logger.error(f"Error in Beer Challenge command: {e}")

    @staticmethod
    def get_success_chance(amount: int) -> int:
        """Return success chance based on input amount."""
        return int(max(1, round(90 * (1 - (amount - 1) / 19) ** 1.5)))

    async def handle_command(self, ctx: Context) -> None:
        """Not used for simple commands."""
        pass
