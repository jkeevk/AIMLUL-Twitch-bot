import random

from twitchio.ext.commands import Context

from src.commands.games.base_game import BaseGame
from src.commands.permissions import is_privileged


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
            cleaned = user_input.strip().split()[0]

            if not cleaned.isdigit():
                await channel.send(f"@{user_name}, че пишешь то? Требуется число от 1 до 20 GAGAGA")
                self.logger.error(f"Invalid input: {user_input}")
                return

            amount = max(1, min(int(cleaned), 20))
            success_chance = self.get_success_chance(amount)
            roll = random.randint(1, 100)

            success = roll <= success_chance
            target_id = await self.cache_manager.get_user_id(user_name, channel_name, self.api)
            if not target_id:
                return
            if success:

                if amount <= 5:
                    msg = f"@{user_name}, разминочная Beerge"
                    tickets_awarded = 1
                elif amount <= 10:
                    msg = f"@{user_name} выпил пивка, освежился и пошел домой PoPivu"
                    tickets_awarded = 2
                elif amount <= 15:
                    msg = f"@{user_name}, куда в тебя столько влезло GIGATON"
                    tickets_awarded = 3
                else:
                    msg = f"@{user_name} - не человек, зверь нахуй NixyiaSobi"
                    tickets_awarded = 5

                await self.db.add_tickets(target_id, user_name, tickets_awarded)
                await channel.send(f"{msg} +{'📜' * tickets_awarded}")

                return

            fail_msgs = [
                f"@{user_name} ушел в пивную кому ystal",
                f"@{user_name} переоценил свои силы, кто убирать будет? CLEAN",
                f"@{user_name} обблевал весь пол и лежит в луже PUKERS",
                f"@{user_name} обблевал весь пол и пополз откисать на диван PUKERS",
            ]
            msg = random.choice(fail_msgs)
            await channel.send(msg)

            if is_privileged(user_name):
                self.logger.warning(f"Privileged user? {user_name}")
                return

            await self.api.timeout_user(
                user_id=target_id, channel_name=channel_name, duration=60, reason="Испытание пивом"
            )

        except Exception as e:
            self.logger.error(f"Error in Beer Challenge command: {e}")

    @staticmethod
    def get_success_chance(amount: int) -> int:
        """Return success chance based on input amount."""
        return int(max(1, round(70 * (1 - (amount - 2) / 19) ** 1.1)))

    async def handle_command(self, ctx: Context) -> None:
        """Not used for simple commands."""
        pass
