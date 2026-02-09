import asyncio
import random
from collections import deque
from typing import Any

from twitchio.ext.commands import Context

from src.commands.games.base_game import BaseGame
from src.commands.models.game_models import GameRank
from src.commands.permissions import PRIVILEGED_USERS
from src.commands.text_inflect import pluralize

PRIVILEGED_USERS_LOWER = {name.lower() for name in PRIVILEGED_USERS}


class TwentyOneGame(BaseGame):
    """
    Twenty-one card game implementation.

    Handles the 21-point card game mechanics including matchmaking,
    scoring, statistics tracking, and leaderboard functionality.
    """

    def __init__(self, command_handler: Any):
        super().__init__(command_handler)

        self.RANKS = GameRank(
            {
                0: "Гном-лудоман",
                10: "Картёжный гоблин",
                20: "Краплёный хряк",
                30: "Гном-картокрад",
                40: "Гоблин-блефун",
                50: "Важный свин",
                60: "Додепный гоблин",
                70: "Чиркаш-мошенник",
                80: "Главный в туза",
                90: "Свин-отыгрун",
                100: "Валетный эксперт",
                120: "Уважаемый очкошник",
                150: "Хряк-виртуоз",
                200: "Король додепа",
                250: "Рисковый очкошник",
                300: "Властелин карт",
                350: "Ставочный барон",
                400: "Главный по додепу",
                450: "Божество очка",
                500: "Абсолютный лудоман",
            }
        )

        self.queue_lock = asyncio.Lock()
        self.player_queue: deque[tuple[str, str]] = deque()
        self.is_processing = False
        self.timer_task: asyncio.Task[Any] | None = None
        self.timer_seconds = 45
        self.last_game_time: float | None = None
        self.is_first_pair = True

    async def handle_command(self, ctx: Context) -> None:
        """
        Handle the main twenty-one game command.

        Args:
            ctx: Command context object
        """
        try:
            user_id = str(ctx.author.id)
            user_name = ctx.author.name

            async with self.queue_lock:
                if any(uid == user_id for uid, _ in self.player_queue):
                    await ctx.send(f"@{user_name} вы уже в очереди! Ждем соперника...")
                    return

                self.player_queue.append((user_id, user_name))
                queue_size = len(self.player_queue)

                self.logger.info(f"{user_name} added to 'очко' queue. Total in queue: {queue_size}")

                if queue_size == 1:
                    await ctx.send(f"@{user_name} ждет соперника для игры в очко! GAMBA")
                    self.is_first_pair = True

                elif queue_size == 2:
                    current_time = asyncio.get_event_loop().time()

                    if self.is_first_pair and (
                        self.last_game_time is None or (current_time - self.last_game_time) >= 45
                    ):
                        if self.timer_task and not self.timer_task.done():
                            self.timer_task.cancel()
                        self.timer_task = asyncio.create_task(self._process_queue_immediately())
                        self.is_first_pair = False
                    else:
                        if self.timer_task is None or self.timer_task.done():
                            self.timer_task = asyncio.create_task(self._process_queue_with_timer())
                # # to inform participants of their queue position
                # else:
                #     position = queue_size
                #     await ctx.send(
                #         f"@{user_name} в очереди! Позиция: {position}. "
                #         f"Следующая игра через {self.timer_seconds} секунд!"
                #     )

        except Exception as e:
            self.logger.error(f"Error adding to queue: {e}")

    async def _process_queue_immediately(self) -> None:
        """Run a game immediately, without waiting, then schedule further games if possible."""
        try:
            await self._process_single_game()

            async with self.queue_lock:
                if len(self.player_queue) >= 2:
                    self.timer_task = asyncio.create_task(self._process_queue_with_timer())

        except Exception as e:
            self.logger.error(f"Error processing queue immediately: {e}")

    async def _process_queue_with_timer(self) -> None:
        """Run games in a loop, waiting `timer_seconds` between them."""
        try:
            while True:
                await asyncio.sleep(self.timer_seconds)

                async with self.queue_lock:
                    if len(self.player_queue) < 2:
                        self.logger.info("Queue is empty, stopping timer")
                        break

                    if self.is_processing:
                        continue

                    await self._process_single_game()

        except asyncio.CancelledError:
            self.logger.info("Queue timer cancelled")
        except Exception as e:
            self.logger.error(f"Queue timer error: {e}")

    async def _process_single_game(self) -> None:
        """Pop two players from the queue and start their game."""
        try:
            self.is_processing = True

            player1_id, player1_name = self.player_queue.popleft()
            player2_id, player2_name = self.player_queue.popleft()

            self.last_game_time = asyncio.get_event_loop().time()

            asyncio.create_task(self._start_game(player1_id, player1_name, player2_id, player2_name))

            remaining_players = len(self.player_queue)
            if remaining_players >= 1:
                channel_name = self.bot.config["channels"][0]
                channel = self.bot.get_channel(channel_name)
                if channel:
                    if remaining_players == 1:
                        next_player_id, next_player_name = self.player_queue[0]
                        await channel.send(f"@{next_player_name} ждет соперника для следующей игры! GAMBA")
                    else:
                        await channel.send(
                            f"В очереди осталось {remaining_players} {pluralize(remaining_players, 'игрок')}. "
                            f"Следующая игра через {self.timer_seconds} секунд!"
                        )
        except Exception as e:
            self.logger.error(f"Error processing single game: {e}")
        finally:
            self.is_processing = False

    async def _start_game(self, player1_id: str, player1_name: str, player2_id: str, player2_name: str) -> None:
        """
        Start a single game between two players.

        Args:
            player1_id: ID of the first player.
            player1_name: Username of the first player.
            player2_id: ID of the second player.
            player2_name: Username of the second player.
        """
        try:
            channel_name = self.bot.config["channels"][0]
            channel = self.bot.get_channel(channel_name)

            if not channel:
                self.logger.error(f"Channel {channel_name} not found")
                return

            score1 = random.randint(16, 24)
            score2 = random.randint(16, 24)

            if score1 == score2:
                await channel.send(
                    f"Джонни Додеп: Ничья! @{player1_name} и @{player2_name} "
                    f"сыграли вничью GAGAGA ({player1_name}: {score1} | {player2_name}: {score2})"
                )
                return

            winner_name, loser_name, winner_id, loser_id = self._determine_winner(
                score1, score2, (player1_id, player1_name), (player2_id, player2_name)
            )

            await self._handle_game_result(
                channel,
                winner_name,
                loser_name,
                winner_id,
                loser_id,
                player1_name,
                player2_name,
                score1,
                score2,
            )

        except Exception as e:
            self.logger.error(f"Error starting game: {e}")

    @staticmethod
    def _determine_winner(
        score1: int,
        score2: int,
        player1_data: tuple[str, str],
        player2_data: tuple[str, str],
    ) -> tuple[str, str, str, str]:
        """
        Determine the winner based on scores and game rules.

        Args:
            score1: First player's score
            score2: Second player's score
            player1_data: Tuple of (player1_id, player1_name)
            player2_data: Tuple of (player2_id, player2_name)

        Returns:
            Tuple of (winner_name, loser_name, winner_id, loser_id)
        """
        p1_id, p1_name = player1_data
        p2_id, p2_name = player2_data

        p1_valid = score1 <= 21
        p2_valid = score2 <= 21

        if p1_valid and p2_valid:
            return (p1_name, p2_name, p1_id, p2_id) if score1 >= score2 else (p2_name, p1_name, p2_id, p1_id)
        elif p1_valid:
            return p1_name, p2_name, p1_id, p2_id
        elif p2_valid:
            return p2_name, p1_name, p2_id, p1_id
        else:
            return (p1_name, p2_name, p1_id, p2_id) if score1 <= score2 else (p2_name, p1_name, p2_id, p1_id)

    async def _handle_game_result(
        self,
        channel: Any,
        winner_name: str,
        loser_name: str,
        winner_id: str,
        loser_id: str,
        player1_name: str,
        player2_name: str,
        score1: int,
        score2: int,
    ) -> None:
        """
        Handle the result of a game: update DB, send a message, timeout loser.

        Args:
            channel: The channel object to send messages.
            winner_name: Winner’s username.
            loser_name: Loser’s username.
            winner_id: Winner’s user ID.
            loser_id: Loser’s user ID.
            player1_name: First player’s name.
            player2_name: Second player’s name.
            score1: First player’s score.
            score2: Second player’s score.
        """
        if self.db:
            try:
                previous_wins, _ = await self.db.get_stats(winner_id)
                previous_rank = self.RANKS.get_rank(previous_wins)

                winner_wins, _ = await self.db.update_stats(winner_id, winner_name, win=True)
                await self.db.update_stats(loser_id, loser_name, win=False)

                new_rank = self.RANKS.get_rank(winner_wins)
                if new_rank != previous_rank:
                    await channel.send(f"🎉 @{winner_name} достиг нового ранга: {new_rank}! 🏆")

            except Exception as e:
                self.logger.error(f"Error saving statistics: {e}")

        await channel.send(
            f"Джонни Додеп: @{winner_name} победил! "
            f"Ааааааай мляяяя NOOOO @{loser_name} ушел за додепом GAGAGA "
            f"({player1_name}: {score1} | {player2_name}: {score2})"
        )

        if loser_name.lower() not in PRIVILEGED_USERS_LOWER:
            try:
                await self.api.timeout_user(
                    user_id=loser_id,
                    channel_name=channel.name,
                    duration=15,
                    reason="очко",
                )
            except Exception as e:
                self.logger.warning(f"Error during timeout: {e}")

    async def handle_me_command(self, ctx: Context) -> None:
        """
        Handle player statistics command.

        Args:
            ctx: Command context
        """
        if not await self.check_cooldown("me"):
            return

        try:
            if self.db is None:
                await ctx.send("Статистика временно недоступна")
                return

            user_id = str(ctx.author.id)
            wins, losses = await self.db.get_stats(user_id)
            total = wins + losses

            wins, losses = await self.db.get_stats(user_id)
            tickets = await self.db.remove_tickets(user_id, 0)

            if total == 0:
                await ctx.send(f"@{ctx.author.name}, у вас еще нет сыгранных игр. Сыграйте первую игру! GAMBA")
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
                f"📜 Билетов: {tickets}"
            )

            if next_rank_wins > 0:
                wins_needed = next_rank_wins - wins
                victory_word = pluralize(wins_needed, "победа")
                message += f"\n🔜 До следующего ранга: {wins_needed} {victory_word}"
            else:
                message += "\n🌟 Вы достигли максимального ранга! Вот же кому-то делать нехуй SubPricege"

            await ctx.send(message)
            await self.update_cooldown("me")

        except Exception as e:
            self.logger.error(f"Error in 'me' command: {e}")
            await ctx.send("Произошла ошибка при получении статистики")

    async def handle_leaders_command(self, ctx: Context) -> None:
        """
        Handle leaderboard display command.

        Args:
            ctx: Command context
        """
        if not await self.check_cooldown("leaders"):
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

            for i, (username, wins, _losses) in enumerate(top_players):
                medal = medals[i] if i < len(medals) else "🏅"
                rank = self.RANKS.get_rank(wins)
                wins_word = pluralize(wins, "победа")
                wins_str = f"{wins} {wins_word}"
                message_lines.append(f"{medal} {username} - {rank} ({wins_str})")

            await ctx.send("\n".join(message_lines))
            await self.update_cooldown("leaders")

        except Exception as e:
            self.logger.error(f"Error in 'leaders' command: {e}")
            await ctx.send("Произошла ошибка при получении рейтинга")

    async def has_tickets(self, twitch_id: str) -> bool:
        """
        Check if a player has at least one ticket.

        Args:
            twitch_id: Twitch ID of the player

        Returns:
            True if a player has 1 or more tickets, False otherwise
        """
        tickets: int = await self.db.remove_tickets(twitch_id, 0)
        return tickets > 0

    async def consume_ticket(self, twitch_id: str) -> None:
        """
        Consume one ticket from the player. Does nothing if a player has 0 tickets.

        Args:
            twitch_id: Twitch ID of the player
        """
        await self.db.remove_tickets(twitch_id, 1)

    async def close(self) -> None:
        """Clean up resources when shutting down."""
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()
            try:
                await self.timer_task
            except asyncio.CancelledError:
                pass
