import logging
import random
import time
from collections import defaultdict

from twitchio import PartialUser, Chatter

from src.api.twitch_api import TwitchAPI
from src.commands.collectors.applecat_collector import ApplecatCollector
from src.commands.collectors.gnome_collector import GnomeCollector
from src.utils.helpers import is_privileged, format_duration, pluralize
import asyncio


class CommandHandler:
    def __init__(self, bot):
        self.bot = bot
        self.api = TwitchAPI(bot)
        self.logger = logging.getLogger(__name__)
        self.command_cooldowns = defaultdict(int)
        self.db = bot.db if hasattr(bot, "db") else None
        self.collectors = {
            "gnome": GnomeCollector(),
            "applecatpanik": ApplecatCollector(),
        }
        self.RANKS = {
            0: "Гном-лудоман",
            10: "Картёжный гоблин",
            20: "Краплёный хряк",
            30: "Гном-картокрад",
            40: "Гоблин-блефун",
            50: "Важный свин",
            60: "Додепный гоблин",
            70: "Хряк покерного стола",
            80: "Уважаемый очкошник",
            90: "Главный очкошник",
        }
        self.previous_ranks = {}

    async def _handle_collector(self, message, collector_type: str) -> None:
        """Обработчик для команд со сбором участников"""
        try:
            if is_privileged(message.author):
                return

            collector = self.collectors[collector_type]

            if collector.should_reset() and collector.participants:
                self.logger.info(f"🔄 Автосброс сборщика {collector_type}")
                collector.reset()

            if not collector.add(message.author.id, message.author.name):
                return

            self.logger.info(
                f"➕ {message.author.name} добавлен в {collector_type}. Всего: {len(collector.participants)}"
            )

            if not collector.is_full():
                return

            target_id, target_name = collector.get_random()
            self.logger.info(
                f"🔨 Попытка таймаута {target_name} ({target_id}) из сбора {collector_type}"
            )

            status, response = await self.api.timeout_user(
                user_id=target_id,
                channel_name=message.channel.name,
                duration=collector.duration,
                reason=collector.reason,
            )

            if status == 200:
                await message.channel.send(
                    collector.timeout_message.format(target_name=target_name)
                )

            collector.reset()

        except Exception as e:
            self.logger.error(
                f"🚨 Ошибка обработки {collector_type}: {e}", exc_info=True
            )

    async def handle_gnome(self, message) -> None:
        """Обрабатывает сообщение GNOME со сбором 5 участников"""
        await self._handle_collector(message, "gnome")

    async def handle_applecat(self, message) -> None:
        """Обрабатывает сообщение applecatPanik со сбором 5 участников"""
        await self._handle_collector(message, "applecatpanik")

    async def handle_drin(self, ctx) -> None:
        """Обрабатывает команду drin"""
        try:
            if not is_privileged(ctx.author):
                self.logger.warning("Отказ: нет привилегий")
                return

            current_time = time.time()
            if (
                current_time - self.command_cooldowns["drin"]
                < self.bot.config["command_delay_time"]
            ):
                return

            valid_chatters = []
            for chatter in ctx.channel.chatters:
                if chatter.name.lower() == self.bot.nick.lower():
                    continue

                if isinstance(chatter, PartialUser):
                    valid_chatters.append(chatter)

                elif isinstance(chatter, Chatter):
                    if not is_privileged(chatter):
                        valid_chatters.append(chatter)

            if not valid_chatters:
                self.logger.warning("🚫 Нет подходящих пользователей для команды 'дрын'")
                return
            target_chatter = random.choice(valid_chatters)
            user_data = await self.bot.fetch_users(names=[target_chatter.name])

            if not user_data:
                self.logger.error(
                    f"❌ Не удалось получить данные пользователя: {target_chatter.name}"
                )
                return

            status, response = await self.api.timeout_user(
                user_id=user_data[0].id,
                channel_name=ctx.channel.name,
                duration=15,
                reason="дрын",
            )

            if status == 200:
                await ctx.send(
                    f"{ctx.author.name} бьёт дрыном по голове {target_chatter.name} MODS"
                )
                self.command_cooldowns["drin"] = current_time
                self.logger.info(f"🪵 Дрын применён к {target_chatter.name}")

        except Exception as e:
            self.logger.error(f"🚨 Ошибка команды 'дрын': {e}", exc_info=True)

    async def handle_zhopa(self, ctx) -> None:
        try:

            current_time = time.time()
            if (
                current_time - self.command_cooldowns["zhopa"]
                < self.bot.config["command_delay_time"]
            ):
                return

            random_chance = random.randint(1, 100)
            privileged = is_privileged(ctx.author)

            if random_chance <= 90:
                message = f"Жопа @{ctx.author.name} воняет на {random_chance}% xdding"
                await ctx.send(message)
                self.command_cooldowns["zhopa"] = current_time
                return

            duration = 600 if random_chance == 100 else 60
            reason = "extreme жопа" if random_chance else "жопа"
            message = (
                (
                    f"Жопа @{ctx.author.name} воняет на все 100% xdding 👑 Амбассадор вони! "
                    f"Отправлен в мойку на {format_duration(duration)} washing"
                )
                if random_chance == 100
                else (
                    f"Жопа @{ctx.author.name} воняет на {random_chance}% xdding "
                    f"Отправлен в мойку на {format_duration(duration)} washing"
                )
            )
            if privileged:
                await ctx.send(
                    message + " (но вы модератор, поэтому только символически)"
                )
                self.logger.info(f"🛡️ Модератор избежал наказания: {ctx.author.name}")
            else:
                user_data = await self.bot.fetch_users(names=[ctx.author.name])
                if not user_data:
                    self.logger.error(
                        f"❌ Не удалось получить ID пользователя: {ctx.author.name}"
                    )
                    return

                status, response = await self.api.timeout_user(
                    user_id=user_data[0].id,
                    channel_name=ctx.channel.name,
                    duration=duration,
                    reason=reason,
                )

                if status == 200:
                    await ctx.send(message)

            self.command_cooldowns["zhopa"] = current_time

        except Exception as e:
            self.logger.error(f"🚨 Ошибка команды 'жопа': {e}", exc_info=True)

    async def close(self):
        """Закрывает ресурсы при завершении"""
        try:
            self.logger.info("🔌 Закрываю ресурсы CommandHandler...")
            await self.api.close()
            self.logger.info("✅ Ресурсы CommandHandler закрыты")
        except Exception as e:
            self.logger.error(f"🚨 Ошибка при закрытии CommandHandler: {e}")

    async def handle_ochko(self, ctx):
        try:
            current_time = time.time()

            if not hasattr(self, "ochko_lock"):
                self.ochko_lock = asyncio.Lock()
                self.ochko_participants = []
                self.ochko_last_added = 0
                self.ochko_cooldown = 0

            if (
                current_time - self.ochko_cooldown
                < self.bot.config["command_delay_time"]
            ):
                return

            async with self.ochko_lock:
                if (
                    current_time - self.ochko_last_added > 360
                    and self.ochko_participants
                ):
                    self.ochko_participants.clear()
                    self.logger.info("🔄 Автосброс участников очко")

                if any(user[0] == ctx.author.id for user in self.ochko_participants):
                    await ctx.send(
                        f"@{ctx.author.name} вы уже в игре! Ждем соперника..."
                    )
                    return

                self.ochko_participants.append((ctx.author.id, ctx.author.name))
                self.ochko_last_added = current_time
                count = len(self.ochko_participants)
                self.logger.info(f"➕ {ctx.author.name} добавлен в очко. Всего: {count}")

                if count < 2:
                    await ctx.send(
                        f"@{ctx.author.name} ждет соперника для игры в очко!"
                    )
                    return

                player1_id, player1_name = self.ochko_participants.pop(0)
                player2_id, player2_name = self.ochko_participants.pop(0)

                player1_id = str(player1_id)
                player2_id = str(player2_id)

                self.ochko_cooldown = current_time

            score1 = random.randint(16, 24)
            score2 = random.randint(16, 24)

            if score1 == score2:
                await ctx.send(
                    f"Джонни Додеп: Ничья! @{player1_name} и @{player2_name} "
                    f"сыграли вничью GAGAGA ({player1_name}: {score1} | {player2_name}: {score2})"
                )
                return

            winner_name, loser_name, winner_id, loser_id = (
                (player1_name, player2_name, player1_id, player2_id)
                if (score1 <= 21 and (score1 > score2 or score2 > 21))
                or (score1 > 21 and score2 > 21 and score1 < score2)
                else (player2_name, player1_name, player2_id, player1_id)
            )

            if self.db:
                try:
                    previous_winner_wins, _ = await self.db.get_stats(str(winner_id))
                    previous_rank = self.get_rank(previous_winner_wins)

                    winner_wins, winner_losses = await self.db.update_stats(
                        str(winner_id), winner_name, win=True
                    )
                    loser_wins, loser_losses = await self.db.update_stats(
                        str(loser_id), loser_name, win=False
                    )

                    new_rank = self.get_rank(winner_wins)

                    if new_rank != previous_rank:
                        await ctx.send(
                            f"🎉 @{winner_name} достиг нового ранга: {new_rank}! "
                            f"Продолжайте играть, чтобы стать {self.get_rank(winner_wins + 10)}! 🏆"
                        )

                    self.logger.info(
                        f"📊 Статистика обновлена: "
                        f"{winner_name} ({winner_wins}/{winner_losses}) | "
                        f"{loser_name} ({loser_wins}/{loser_losses})"
                    )
                except Exception as e:
                    self.logger.error(f"🚨 Ошибка сохранения статистики: {e}")
            else:
                self.logger.warning(
                    "❌ База данных недоступна для сохранения статистики"
                )

            await ctx.send(
                f"Джонни Додеп: @{winner_name} победил! "
                f"Ааааааай мляяяяя NOOOO @{loser_name} ушел за додепом GAGAGA "
                f"({player1_name}: {score1} | {player2_name}: {score2})"
            )

            loser_is_mod = any(
                chatter.name.lower() == loser_name.lower() and is_privileged(chatter)
                for chatter in ctx.channel.chatters
            )

            if not loser_is_mod:
                status, response = await self.api.timeout_user(
                    user_id=loser_id,
                    channel_name=ctx.channel.name,
                    duration=15,
                    reason="очко",
                )
                if status == 200:
                    self.logger.info(f"⏳ Таймаут 15s для {loser_name}")

        except Exception as e:
            self.logger.error(f"🚨 Ошибка в команде !очко: {e}", exc_info=True)

    async def handle_me(self, ctx):
        """Обработка команды !я для вывода статистики"""
        current_time = time.time()

        if (
            current_time - self.command_cooldowns["me"]
            < self.bot.config["command_delay_time"]
        ):
            return

        try:
            if self.db is None:
                await ctx.send("Статистика временно недоступна")
                return

            user_id = str(ctx.author.id)
            wins, losses = await self.db.get_stats(user_id)
            total = wins + losses

            if total == 0:
                wins, losses = await self.db.update_stats(
                    user_id, ctx.author.name, win=False
                )
                total = 1

            win_rate = (wins / total) * 100
            rank = self.get_rank(wins)
            next_rank_wins = min([t for t in self.RANKS.keys() if t > wins], default=0)

            wins_word = pluralize(wins, "победа")
            losses_word = pluralize(losses, "поражение")

            message = (
                f"@{ctx.author.name}, ваш ранг: {rank} "
                f"(🏆 {wins} {wins_word} | 💀 {losses} {losses_word})\n"
                f"📊 Процент побед: {win_rate:.1f}%"
            )

            if next_rank_wins > 0:
                wins_needed = next_rank_wins - wins
                victory_word = pluralize(wins_needed, "победа")
                message += f"\n🔜 До следующего ранга: {wins_needed} {victory_word}"

            await ctx.send(message)
            self.command_cooldowns["me"] = current_time

        except Exception as e:
            self.logger.error(f"🚨 Ошибка команды 'я': {e}", exc_info=True)
            await ctx.send("Произошла ошибка при получении статистики")

    def get_rank(self, wins: int) -> str:
        """Возвращает текущий ранг по количеству побед"""
        sorted_thresholds = sorted(self.RANKS.keys(), reverse=True)
        for threshold in sorted_thresholds:
            if wins >= threshold:
                return self.RANKS[threshold]
        return self.RANKS[0]

    async def handle_leaders(self, ctx):
        """Обработка команды !лидеры для вывода топ-3 игроков"""
        current_time = time.time()

        if (
            current_time - self.command_cooldowns["leaders"]
            < self.bot.config["command_delay_time"]
        ):
            return

        try:
            if self.db is None:
                await ctx.send("Статистика временно недоступна")
                return

            top_players = await self.db.get_top_players(limit=3)
            if not top_players:
                await ctx.send("📊 Рейтинг пока пуст")
                return

            medals = ["🥇", "🥈", "🥉"]
            message_lines = ["Главные очкошники: "]

            for i, (username, wins, losses) in enumerate(top_players):
                if i < len(medals):
                    medal = medals[i]
                else:
                    medal = "🏅"

                wins_word = pluralize(wins, "победа")
                wins_str = f"{wins} {wins_word}"

                message_lines.append(f"{medal} {username} ({wins_str})")

            await ctx.send("\n".join(message_lines))
            self.command_cooldowns["leaders"] = current_time

        except Exception as e:
            self.logger.error(f"🚨 Ошибка команды 'лидеры': {e}", exc_info=True)
            await ctx.send("Произошла ошибка при получении рейтинга")
