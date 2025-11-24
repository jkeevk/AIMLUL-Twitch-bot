import asyncio
import random
import time

from twitchio.ext.commands import Context

from src.commands.games.base_game import BaseGame
from src.commands.permissions import is_privileged
from src.commands.text_inflect import format_duration


class SimpleCommandsGame(BaseGame):
    """Handles simple chat commands like club, butt, and test barrel."""

    async def handle_club_command(self, ctx: Context) -> None:
        """
        Handle the club command for moderators.

        Args:
            ctx: Command context object
        """
        try:
            if not is_privileged(ctx.author):
                self.logger.warning("Access denied: insufficient privileges")
                return

            if not self.check_cooldown("club"):
                return

            if self.cache_manager.should_update_cache():
                asyncio.create_task(self.cache_manager.update_chatters_cache(ctx.channel, self.bot.nick))
                if not self.cache_manager.get_cached_chatters():
                    await self.cache_manager.update_chatters_cache(ctx.channel, self.bot.nick)

            cached_chatters = self.cache_manager.get_cached_chatters()
            if not cached_chatters:
                self.logger.warning("No suitable users found for club command")
                return

            target_chatter = random.choice(cached_chatters)
            target_id = await self.user_manager.get_user_id(target_chatter.name, target_chatter)

            if not target_id:
                self.logger.error(f"Failed to get user ID: {target_chatter.name}")
                return

            timeout_task = asyncio.create_task(
                self.api.timeout_user(
                    user_id=target_id,
                    channel_name=ctx.channel.name,
                    duration=15,
                    reason="дрын",
                )
            )

            await ctx.send(f"{ctx.author.name} бьёт дрыном по голове {target_chatter.name} MODS")
            status, response = await timeout_task

            if status == 200:
                self.update_cooldown("club")
                self.logger.info(f"Club applied to {target_chatter.name}")
                asyncio.create_task(self.cache_manager.update_chatters_cache(ctx.channel, self.bot.nick))
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
            if not self.check_cooldown("butt"):
                return

            random_chance = random.randint(1, 100)
            privileged = is_privileged(ctx.author)

            if random_chance < 90:
                message = f"Жопа @{ctx.author.name} воняет на {random_chance}% xdding"
                await ctx.send(message)
                self.update_cooldown("butt")
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
                self.update_cooldown("butt")
            else:
                target_id = await self.user_manager.get_user_id(ctx.author.name, ctx.author)
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
                    self.update_cooldown("butt")
                else:
                    self.logger.warning(f"Timeout failed: {status}")

        except Exception as e:
            self.logger.error(f"Butt command error: {e}")

    async def handle_test_barrel_command(self, ctx: Context) -> None:
        """
        Handle test barrel command for administrators.

        Args:
            ctx: Command context object
        """
        start_time = time.time()
        try:
            if ctx.author.name.lower() not in self.bot.config.get("admins", []):
                self.logger.warning(f"Unauthorized barrel attempt: {ctx.author.name}")
                return

            if not self.check_cooldown("test_barrel"):
                return

            valid_chatters = self.cache_manager.filter_chatters(ctx.channel.chatters)
            if not valid_chatters:
                self.logger.warning("No suitable users for barrel command")
                return

            selected_count = min(10, len(valid_chatters))
            targets = random.sample(valid_chatters, selected_count)

            timeout_tasks = []
            for target in targets:
                target_id = await self.user_manager.get_user_id(target.name, target)
                if target_id:
                    timeout_tasks.append(
                        self.api.timeout_user(
                            user_id=target_id,
                            channel_name=ctx.channel.name,
                            duration=15,
                            reason="Тестовая бочка",
                        )
                    )

            if not timeout_tasks:
                self.logger.error("Failed to get user IDs")
                return

            results = await asyncio.gather(*timeout_tasks, return_exceptions=True)
            punished_users = []

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"Error processing {targets[i].name}: {result}")
                    continue

                if isinstance(result, tuple) and len(result) == 2:
                    status, response = result
                    if status == 200:
                        punished_users.append(targets[i].name)
                else:
                    self.logger.warning(f"Unexpected result type for {targets[i].name}: {type(result)}")

            if punished_users:
                names_list = ", ".join(f"@{name}" for name in punished_users)
                message = f"{ctx.author.name} Тест. По пиздаку получили: {names_list}"
            else:
                message = f"{ctx.author.name} Тест. Бочка дала осечку!"

            await ctx.send(message)
            self.update_cooldown("test_barrel")
            self.logger.info(f"Test barrel completed. Successful: {len(punished_users)}")

        except Exception as e:
            self.logger.error(f"Critical error in test barrel: {e}")
        finally:
            execution_time = (time.time() - start_time) * 1000
            if execution_time > 500:
                self.logger.info(f"Test barrel execution time: {execution_time:.2f}ms")

    async def handle_command(self, ctx: Context) -> None:
        """Not used for simple commands."""
        pass
