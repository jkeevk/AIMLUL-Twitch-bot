import asyncio
import random
import time
from typing import Any

from twitchio.ext.commands import Context

from src.commands.games.base_game import BaseGame

MAX_MESSAGE_LENGTH = 255


class BeerBarrelGame(BaseGame):
    """Handles the Beer Barrel reward without requiring a chat context."""

    _is_running: bool = False
    active_players: set[str] = set()
    kaban_players: set[str] = set()
    KABAN_TARGET_COUNT: int = 10
    KABAN_TIME_LIMIT: int = 60

    async def _send_batched_message(self, channel: Any, prefix: str, names: list[str] | set[str]) -> None:
        """
        Splits a list of usernames into chunks and sends them to the channel,
        ensuring each message does not exceed MAX_MESSAGE_LENGTH.
        """
        if not names:
            return

        current_message = prefix

        if isinstance(names, set):
            names = list(names)

        for name in names:
            mention = f"@{name}, "

            if len(current_message) + len(mention) > MAX_MESSAGE_LENGTH:
                await channel.send(current_message.rstrip(", "))
                current_message = mention
            else:
                current_message += mention

        if current_message.strip() and current_message != prefix:
            await channel.send(current_message.rstrip(", "))

    async def _run_kaban_challenge_and_determine_fate(self, channel: Any) -> bool:
        """
        Runs the Kaban Challenge timer, integrates visual countdown (ASCII/messages),
        and executes the final roll based on Kaban success.

        Returns: True if the standard punishment should be executed, False otherwise.
        """
        channel_name = channel.name
        challenge_success = False

        self.logger.info(f"Kaban Challenge started for {self.KABAN_TIME_LIMIT} seconds in {channel_name}")

        ascii_art_start = "⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⠉⠀⠀⠀⠉⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡏⠀⠀⠀⠀⠀⠀⠀⠸⠉⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⡿⢿⣿⡿⠓⠀⠀⡎⠉⠉⢢⠀⠀⠀⠀⠛⢿⠋⢻⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣤⣤⣿⡀⠀⠀⠀⠓⠴⠃⣼⠀⠀⠀⠀⠀⢸⣿⠁⣸⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⠀⢹⣿⠒⠒⠒⠒⠒⠚⢿⠀⣤⣄⠀⢸⣛⣛⠛⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣶⠛⣿⡄⠀⣀⠀⠀⣀⣼⠀⣧⡈⠷⢾⣿⣿⡇⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⡏⠀⠀⡏⢿⣀⣿⠁⠀⢸⣿⣿⡇⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⡇⠀⠀⡇⠀⠉⣿⠀⠀⢸⣿⣿⡇⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⡇⠀⠀⡇⠀⠀⣿⠀⠀⢸⣋⣉⣁⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⡇⠀⠀⡇⠀⠀⣿⠀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⡇⠀⠀⡇⠀⠀⣿⠀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⢸⣇⠀⠀⣧⠀⠀⣿⡀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣇⠀⠁⠀⠀⠈⠀⠀⠈⠀⢀⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿"  # noqa: E501
        await channel.send(ascii_art_start)
        await channel.send("catLicks ПРИГОТОВИЛИСЬ! ДО ВСКРЫТИЯ ПИВНОЙ КЕГИ 60 СЕКУНД! catLicks")
        await asyncio.sleep(2)
        await channel.send(
            f"DinkDonk Начинается 'Прибежать кабанчиком на пиво KabanRunZaPivom '! Нужно {self.KABAN_TARGET_COUNT} героев, чтобы обезвредить кегу!"
        )

        await asyncio.sleep(18)

        current_count = len(self.kaban_players)
        if current_count >= self.KABAN_TARGET_COUNT and not challenge_success:
            challenge_success = True
            self.logger.info("Kaban Challenge succeeded early!")

        if current_count > 0 and current_count < self.KABAN_TARGET_COUNT:
            remaining_needed = self.KABAN_TARGET_COUNT - current_count
            await channel.send(
                f"MadgeTime Осталось 40 секунд до взрыва! Собрано {current_count}/{self.KABAN_TARGET_COUNT}. Нужно еще {remaining_needed}!"
            )

        await asyncio.sleep(20)

        current_count = len(self.kaban_players)
        if current_count >= self.KABAN_TARGET_COUNT and not challenge_success:
            challenge_success = True
            self.logger.info("Kaban Challenge succeeded early!")

        if current_count > 0 and current_count < self.KABAN_TARGET_COUNT:
            remaining_needed = self.KABAN_TARGET_COUNT - current_count
            await channel.send(
                f"MadgeTime Осталось 20 секунд до взрыва! Собрано {current_count}/{self.KABAN_TARGET_COUNT}. Нужно еще {remaining_needed}!"
            )

        await asyncio.sleep(10)
        await channel.send("catLicks ГОТОВЬТЕ КРУЖКИ! 10 СЕКУНД catLicks")
        await asyncio.sleep(4)
        final_count = len(self.kaban_players)
        if final_count >= self.KABAN_TARGET_COUNT:
            challenge_success = True

        if challenge_success:
            await channel.send("Кабанчики прибыли в полном составе! Gregories")
        await asyncio.sleep(5)
        await channel.send("Кто тащил кегу??? Wigglecat Прячься, сейчас пизданёт KabanRunZaPivom")
        await asyncio.sleep(1)

        if not challenge_success:
            await channel.send(f"NOOOO Не хватило кабанчиков ({final_count}/{self.KABAN_TARGET_COUNT}) damn")
            await asyncio.sleep(1)
            return True

        is_roll_successful = random.choice([True, False])

        if is_roll_successful:
            self.logger.info("50/50 Roll: SUCCESS! Keg is neutralized.")

            if final_count > 0:
                prefix = "ПОБЕДА peepoClap Подпивасов прогнали эти герои: "
                await self._send_batched_message(channel, prefix, self.kaban_players)

            await asyncio.sleep(3)
            return False
        else:
            self.logger.info("50/50 Roll: FAILURE! Standard barrel execution triggered.")
            await channel.send("ПОРАЖЕНИЕ upal Кабанчики прибыли но не осилили кегу!")
            await asyncio.sleep(1)
            return True

    async def handle_beer_barrel_command(self, user_name: str, channel_name: str) -> None:
        """
        Initiates the Beer Barrel event, selects targets, executes timeouts,
        and announces results.
        """
        self._is_running = True
        self.active_players.clear()
        self.kaban_players.clear()

        try:
            if self.cache_manager.should_update_cache():
                chatters: list[dict[str, Any]] = await self.api.get_chatters(channel_name)
                normalized: list[dict[str, str]] = [
                    {"id": c["user_id"], "name": c["user_name"], "display_name": c["user_name"]} for c in chatters
                ]
                self.cache_manager._cached_chatters = self.cache_manager.filter_chatters(normalized)
                self.cache_manager._last_cache_update = time.time()

            valid_chatters: list[dict[str, str]] = self.cache_manager.get_cached_chatters()
            random.shuffle(valid_chatters)
            self.logger.info(f"Available chatters for selection: {len(valid_chatters)}")

            if not valid_chatters:
                self.logger.warning("No suitable users for barrel command.")
                return

            selected_count = min(50, len(valid_chatters))

            all_initial_targets: list[dict[str, str]] = random.sample(valid_chatters, selected_count)
            initial_target_names_lower: set[str] = {t["name"].lower() for t in all_initial_targets}
            self.logger.info(f"Initial targets selected: {len(all_initial_targets)}")

            channel = self.bot.get_channel(channel_name)
            if not channel:
                await self.bot.join_channels([channel_name])
                channel = self.bot.get_channel(channel_name)

            should_punish = await self._run_kaban_challenge_and_determine_fate(channel)

            if not should_punish:
                await asyncio.sleep(5)
                self.logger.info("Beer barrel completed (Neutralized by Kaban Challenge).")
                return

            async def process_timeout(target: dict[str, str]) -> str | None:
                target_id = target.get("id")
                target_name = target.get("name")
                try:
                    if not target_id or not target_name:
                        return None

                    status, _ = await self.api.timeout_user(
                        user_id=target_id,
                        channel_name=channel_name,
                        duration=600,
                        reason="Пивная кома",
                    )

                    if status == 200:
                        return str(target_name)
                    else:
                        self.logger.debug(f"Skipping {target_name}: cannot be timed out (status={status})")
                        return None
                except Exception as err:
                    self.logger.error(f"Error processing {target_name or 'unknown'}: {err}")
                    return None

            ascii_art_end = "⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠟⠛⠛⠋⠋⠙⠻⠛⠿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⣿⣿⣿⣿⣿⣿⠟⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠹⢿⣿⣿⣿⣿⣿⣿ ⣿⣿⠿⠛⠁⠀⠀⠀⠀⢀⣠⣠⠄⢀⣄⣀⠀⣤⣴⣆⠀⠀⠀⣼⣿⣿⣿⣿⣿⣿ ⠟⠋⢀⠀⢠⡗⠂⠀⠀⢂⠎⣠⠶⢿⣿⣿⣿⣿⣿⣿⣷⣾⣿⣿⣿⣿⣿⣿⣿⣿ ⠀⢠⣦⠿⠛⠀⠀⡄⠀⠈⠀⠉⠀⠘⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⠀⠀⠉⠀⠀⠀⠀⠁⠀⠀⠀⢀⣠⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠈⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿ ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠙⠿⢿⣿⣿⣿⣿⣿⣿⣿⣿⠿⠋ ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⣀⣉⣩⣩⣄⣀⣠⣤⣤ ⠀⠀⠀⠀⠀⠀⢠⣼⣦⣦⣄⠀⠀⠰⢦⣤⣤⣀⣀⣀⣀⣀⣀⣚⣛⣛⣻⣻⣿⣿"  # noqa: E501
            await channel.send(ascii_art_end)
            await asyncio.sleep(1)

            active_players_lower: set[str] = {name.lower() for name in self.active_players}
            targets_to_punish: list[dict[str, str]] = [
                t for t in all_initial_targets if t["name"].lower() not in active_players_lower
            ]

            punished_users: list[str] = []
            self.logger.info(f"Targets selected for punishment (after filter): {len(targets_to_punish)}")

            batch_size = 10
            for i in range(0, len(targets_to_punish), batch_size):
                batch = targets_to_punish[i : i + batch_size]
                tasks = [process_timeout(target) for target in batch]
                results = await asyncio.gather(*tasks)
                for result in results:
                    if result:
                        punished_users.append(result)
                if i + batch_size < len(targets_to_punish):
                    await asyncio.sleep(0.5)

            if punished_users:
                prefix = f"@{user_name} напоил пивасом Beerge В алкокому впали: "
                await self._send_batched_message(channel, prefix, punished_users)

            await asyncio.sleep(1)
            await channel.send("raveCat Здоровья подпивасам raveCat")

            await asyncio.sleep(1)

            survived_targets: list[str] = [name for name in active_players_lower if name in initial_target_names_lower]
            bought_air: set[str] = active_players_lower - initial_target_names_lower

            self.logger.info(f"Survived targets (Protected): {survived_targets}")
            self.logger.info(f"Bought Air (Wasted money): {bought_air}")

            await asyncio.sleep(5)

            if survived_targets:
                prefix = "ICANT Помойные но живые: "
                await self._send_batched_message(channel, prefix, survived_targets)

            await asyncio.sleep(1)

            if bought_air:
                prefix = "GAGAGA Купили воздух за 800: "
                await self._send_batched_message(channel, prefix, bought_air)

            self.logger.info(f"Beer barrel completed. Successful punishments: {len(punished_users)}")

        except Exception as e:
            self.logger.error(f"Critical error in beer barrel event: {e}")
        finally:
            self.kaban_players.clear()
            self.active_players.clear()
            self._is_running = False

    async def handle_trash_command(self, user_name: str, channel_name: str) -> None:
        """
        Allows a player to activate the 'Hide in a trash bin' command to protect themselves
        from the Beer Barrel event.
        """
        if not self._is_running:
            self.logger.info(f"{user_name} attempted to protect but barrel is not running")
            return

        if user_name in self.active_players:
            self.logger.info(f"{user_name} is already protected")
            return

        self.active_players.add(user_name)
        self.logger.info(f"{user_name} activated protection in {channel_name}")

    async def handle_kaban_command(self, user_name: str, channel_name: str) -> None:
        """
        Allows a player to join the 'Kaban Challenge' to neutralize the barrel.
        """
        if not self._is_running:
            self.logger.info(f"{user_name} attempted to join Kaban Challenge, but barrel is not running.")
            return

        if len(self.kaban_players) >= self.KABAN_TARGET_COUNT:
            self.logger.info(f"{user_name} tried to join, but the Kaban team is already full.")
            return

        if user_name in self.kaban_players:
            self.logger.info(f"{user_name} already joined the Kaban Challenge.")
            return

        self.kaban_players.add(user_name)
        self.logger.info(f"{user_name} joined the Kaban Challenge in {channel_name}. Count: {len(self.kaban_players)}")

    async def handle_command(self, ctx: Context) -> None:
        """Not used for simple commands."""
        pass
