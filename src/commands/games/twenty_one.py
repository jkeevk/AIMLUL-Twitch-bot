import random
import asyncio
import time

from src.commands.games.base_game import BaseGame
from src.commands.models.game_models import GameRank
from src.utils.helpers import is_privileged, pluralize


class TwentyOneGame(BaseGame):
    """Игра в 21 очко"""

    def __init__(self, command_handler):
        super().__init__(command_handler)

        self.RANKS = GameRank({
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
        })

        # Игровые атрибуты
        self.twenty_one_lock = asyncio.Lock()
        self.twenty_one_participants = []
        self.twenty_one_last_added = 0
        self.twenty_one_cooldown = 0

    async def handle_command(self, ctx) -> None:
        """Обработка команды !очко"""
        start_time = time.time()
        try:
            current_time = self.command_handler.get_current_time()

            # Проверяем глобальный кулдаун команды !очко
            if not self.check_cooldown("twenty_one"):
                return

            async with self.twenty_one_lock:
                if (current_time - self.twenty_one_last_added > 360 and
                        self.twenty_one_participants):
                    self.twenty_one_participants.clear()
                    self.logger.info("🔄 Автосброс участников очко")

                if any(user[0] == ctx.author.id for user in self.twenty_one_participants):
                    await ctx.send(f"@{ctx.author.name} вы уже в игре! Ждем соперника...")
                    return

                self.twenty_one_participants.append((str(ctx.author.id), ctx.author.name))
                self.twenty_one_last_added = current_time
                count = len(self.twenty_one_participants)
                self.logger.info(f"➕ {ctx.author.name} добавлен в очко. Всего: {count}")

                if count < 2:
                    await ctx.send(f"@{ctx.author.name} ждет соперника для игры в очко!")
                    return

                player1_id, player1_name = self.twenty_one_participants.pop(0)
                player2_id, player2_name = self.twenty_one_participants.pop(0)
                self.twenty_one_cooldown = current_time

            score1 = random.randint(16, 24)
            score2 = random.randint(16, 24)

            if score1 == score2:
                await ctx.send(
                    f"Джонни Додеп: Ничья! @{player1_name} и @{player2_name} "
                    f"сыграли вничью GAGAGA ({player1_name}: {score1} | {player2_name}: {score2})"
                )
                self.update_cooldown("twenty_one")  # Обновляем кулдаун даже при ничье
                return

            winner_name, loser_name, winner_id, loser_id = self._determine_winner(
                score1, score2,
                (player1_id, player1_name),
                (player2_id, player2_name)
            )

            await self._handle_game_result(ctx, winner_name, loser_name, winner_id, loser_id,
                                           player1_name, player2_name, score1, score2)

            self.update_cooldown("twenty_one")  # Обновляем кулдаун после завершения игры

        except Exception as e:
            self.logger.error(f"🚨 Ошибка в команде !очко: {e}")
        finally:
            execution_time = (time.time() - start_time) * 1000
            if execution_time > 500:
                self.logger.info(f"⏱️ Время выполнения !очко: {execution_time:.2f}ms")

    def _determine_winner(self, score1: int, score2: int, player1_data: tuple, player2_data: tuple) -> tuple:
        """Определяет победителя в игре 21"""
        p1_id, p1_name = player1_data
        p2_id, p2_name = player2_data

        p1_valid = score1 <= 21
        p2_valid = score2 <= 21

        if p1_valid and p2_valid:
            return (p1_name, p2_name, p1_id, p2_id) if score1 >= score2 else (p2_name, p1_name, p2_id, p1_id)
        elif p1_valid:
            return (p1_name, p2_name, p1_id, p2_id)
        elif p2_valid:
            return (p2_name, p1_name, p2_id, p1_id)
        else:
            return (p1_name, p2_name, p1_id, p2_id) if score1 <= score2 else (p2_name, p1_name, p2_id, p1_id)

    async def _handle_game_result(self, ctx, winner_name: str, loser_name: str, winner_id: str, loser_id: str,
                                  player1_name: str, player2_name: str, score1: int, score2: int) -> None:
        """Обрабатывает результат игры"""
        if self.db:
            try:
                previous_winner_wins, _ = await self.db.get_stats(winner_id)
                previous_rank = self.RANKS.get_rank(previous_winner_wins)

                winner_wins, winner_losses = await self.db.update_stats(winner_id, winner_name, win=True)
                loser_wins, loser_losses = await self.db.update_stats(loser_id, loser_name, win=False)

                new_rank = self.RANKS.get_rank(winner_wins)

                if new_rank != previous_rank:
                    await ctx.send(
                        f"🎉 @{winner_name} достиг нового ранга: {new_rank}! "
                        f"Продолжайте играть, чтобы стать {self.RANKS.get_rank(winner_wins + 10)}! 🏆"
                    )

                self.logger.info(
                    f"📊 Статистика обновлена: {winner_name} ({winner_wins}/{winner_losses}) | "
                    f"{loser_name} ({loser_wins}/{loser_losses})"
                )
            except Exception as e:
                self.logger.error(f"🚨 Ошибка сохранения статистики: {e}")

        await ctx.send(
            f"Джонни Додеп: @{winner_name} победил! "
            f"Ааааааай мляяяяя NOOOO @{loser_name} ушел за додепом GAGAGA "
            f"({player1_name}: {score1} | {player2_name}: {score2})"
        )

        # Таймаут для проигравшего
        loser_is_mod = any(
            chatter.name.lower() == loser_name.lower() and is_privileged(chatter)
            for chatter in self.cache_manager.get_cached_chatters()
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

    async def handle_me_command(self, ctx) -> None:
        """Обработка команды !я для статистики"""
        if not self.check_cooldown("me"):
            return

        try:
            if self.db is None:
                await ctx.send("Статистика временно недоступна")
                return

            user_id = str(ctx.author.id)
            wins, losses = await self.db.get_stats(user_id)
            total = wins + losses

            if total == 0:
                await ctx.send(f"@{ctx.author.name}, у вас еще нет сыгранных игр. Сыграйте первую игру!")
                return

            win_rate = (wins / total) * 100
            rank = self.RANKS.get_rank(wins)
            next_rank_wins = min([t for t in self.RANKS.thresholds.keys() if t > wins], default=0)

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
            self.update_cooldown("me")

        except Exception as e:
            self.logger.error(f"🚨 Ошибка команды 'я': {e}")
            await ctx.send("Произошла ошибка при получении статистики")

    async def handle_leaders_command(self, ctx) -> None:
        """Обработка команды !лидеры"""
        if not self.check_cooldown("leaders"):
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
                medal = medals[i] if i < len(medals) else "🏅"
                wins_word = pluralize(wins, "победа")
                wins_str = f"{wins} {wins_word}"
                message_lines.append(f"{medal} {username} ({wins_str})")

            await ctx.send("\n".join(message_lines))
            self.update_cooldown("leaders")

        except Exception as e:
            self.logger.error(f"🚨 Ошибка команды 'лидеры': {e}")
            await ctx.send("Произошла ошибка при получении рейтинга")