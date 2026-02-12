import random
import time
from typing import Any

from twitchio.ext.commands import Context

from src.commands.games.base_game import BaseGame
from src.commands.permissions import is_privileged
from src.commands.text_inflect import format_duration

VOTEBAN_REQUIRED_VOTES = 10
VOTEBAN_WINDOW_SECONDS = 300
VOTEBAN_TIMEOUT_SECONDS = 300


class SimpleCommandsGame(BaseGame):
    """Handles simple chat commands like club, butt, and voteban."""

    async def handle_club_command(self, ctx: Context) -> None:
        """
        Handle the club command for moderators.

        Chooses a random active chatter and applies a 15s timeout,
        unless the target is privileged. If the author hits themselves,
        a special message is sent instead.
        """
        try:
            if not is_privileged(ctx.author):
                self.logger.warning("Access denied: insufficient privileges")
                return

            if not await self.check_cooldown("club"):
                return

            channel = ctx.channel.name
            author_name = ctx.author.name
            author_lower = author_name.lower()

            active_users = await self.cache_manager.get_active_chatters(channel)

            if active_users:
                target = random.choice(active_users)
                target_name = target["name"]
                target_id = target.get("id")
            else:
                cached_chatters = await self.cache_manager.get_or_update_chatters(
                    channel,
                    self.api,
                )
                if not cached_chatters:
                    return

                target = random.choice(cached_chatters)
                target_name = target.name
                target_id = target.id

            if target_name.lower() == author_lower:
                await ctx.send(f"{author_name} бьёт дрыном по голове сам себя GAGAGA Вот же фрик чвч")
                await self.update_cooldown("club")
                return

            await ctx.send(f"{author_name} бьёт дрыном по голове {target_name} MODS")
            await self.update_cooldown("club")

            if is_privileged(target_name):
                self.logger.info(f"Skipping timeout for privileged user: {target_name}")
                return

            if not target_id:
                target_id = await self.cache_manager.get_user_id(target_name, channel, self.api)

            if not target_id:
                self.logger.warning(f"No target id found for {target_name}")
                return

            status, _ = await self.api.timeout_user(
                user_id=target_id,
                channel_name=channel,
                duration=15,
                reason="дрын",
            )

            if status == 200:
                self.logger.info(f"Club applied to {target_name}")
            else:
                self.logger.warning(f"Timeout failed: {status}")

        except Exception as e:
            self.logger.error(f"Club command error: {e}")

    async def handle_butt_command(self, ctx: Context) -> None:
        """
        Handle the butt command with random chance mechanics.

        Args:
            ctx: Command context object
        """
        try:
            if not await self.check_cooldown("butt"):
                return

            random_chance = random.randint(1, 100)
            privileged = is_privileged(ctx.author)

            if random_chance < 90:
                message = f"Жопа @{ctx.author.name} воняет на {random_chance}% xdding"
                await ctx.send(message)
                await self.update_cooldown("butt")
                return

            duration = 600 if random_chance == 100 else 60
            reason = "extreme жопа" if random_chance == 100 else "жопа"
            message = (
                f"Жопа @{ctx.author.name} воняет на все 100% xdding 👑 Амбассадор вони! "
                f"Отправлен в мойку на {format_duration(duration)} washing"
                if random_chance == 100
                else f"Жопа @{ctx.author.name} воняет на {random_chance}% xdding "
                f"Отправлен в мойку на {format_duration(duration)} washing"
            )

            if privileged:
                await ctx.send(message + " Шучу, не отправлен калик)")
                self.logger.info(f"Moderator avoided punishment: {ctx.author.name}")
                await self.update_cooldown("butt")
            else:
                target_id = ctx.author.id
                if not target_id:
                    self.logger.error(f"Failed to get user ID: {ctx.author.name}")
                    return
                status, response = await self.api.timeout_user(
                    user_id=target_id,
                    channel_name=ctx.channel.name,
                    duration=duration,
                    reason=reason,
                )

                if status == 200:
                    await ctx.send(message)
                    await self.update_cooldown("butt")
                else:
                    self.logger.warning(f"Timeout failed: {status}")

        except Exception as e:
            self.logger.error(f"Butt command error: {e}")

    async def handle_voteban_command(self, ctx: Context) -> None:
        """
        Handle the !voteban command to vote for a user to be timed out.

        Tracks votes, prevents self-voting, and applies the timeout
        when the required number of votes is reached.

        Args:
            ctx: Command context object
        """
        try:
            now = time.time()
            parts = ctx.message.content.split()
            if len(parts) < 2:
                return

            target_name = parts[1].lstrip("@").lower()
            voter_name = ctx.author.name.lower()

            if target_name == voter_name or not target_name:
                return

            state = self.command_handler.voteban_state

            if state.get("target") and now - state.get("start_time", 0) > VOTEBAN_WINDOW_SECONDS:
                self._reset_voteban_state(state)

            if state["target"] != target_name:
                state["target"] = target_name
                state["votes"] = set()
                state["start_time"] = now

            if voter_name in state["votes"]:
                return

            state["votes"].add(voter_name)
            votes_count = len(state["votes"])

            self.logger.info(f"VoteBan vote: {voter_name} → {target_name} " f"({votes_count}/{VOTEBAN_REQUIRED_VOTES})")

            if votes_count < VOTEBAN_REQUIRED_VOTES:
                return

            target_id = await self.cache_manager.get_user_id(target_name, ctx.channel.name, self.api)
            if not target_id:
                self._reset_voteban_state(state)
                return

            status, _ = await self.api.timeout_user(
                user_id=target_id,
                channel_name=ctx.channel.name,
                duration=VOTEBAN_TIMEOUT_SECONDS,
                reason="voteban",
            )

            if status == 200:
                await ctx.send(
                    f"Jokerge Чат решил! @{target_name} изгнан на {VOTEBAN_TIMEOUT_SECONDS // 60} минут "
                    f"({votes_count}/{VOTEBAN_REQUIRED_VOTES} голосов)"
                )
            else:
                self.logger.warning(f"!voteban timeout failed: {status}")

            self._reset_voteban_state(state)

        except Exception as e:
            self.logger.error(f"VoteBan error: {e}", exc_info=True)

    @staticmethod
    def _reset_voteban_state(state: dict[str, Any]) -> None:
        """
        Reset the voteban state to start a new vote.

        Args:
            state: The voteban state dictionary to reset
        """
        state["target"] = None
        state["votes"].clear()
        state["start_time"] = 0

    async def handle_command(self, ctx: Context) -> None:
        """Not used for simple commands."""
        pass
