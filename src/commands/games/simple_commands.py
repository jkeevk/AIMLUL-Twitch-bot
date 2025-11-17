import random
import time
import asyncio

from src.commands.games.base_game import BaseGame
from src.utils.helpers import format_duration, is_privileged


class SimpleCommandsGame(BaseGame):
    """Простые команды (дрын, жопа, бочка)"""

    async def handle_club_command(self, ctx) -> None:
        """Обработка команды !дрын"""
        start_time = time.time()
        try:
            if not is_privileged(ctx.author):
                self.logger.warning("Отказ: нет привилегий")
                return

            # Проверяем кулдаун команды
            if not self.check_cooldown("club"):
                return

            # Обновляем кэш если нужно
            if self.cache_manager.should_update_cache():
                asyncio.create_task(
                    self.cache_manager._update_chatters_cache(ctx.channel, self.bot.nick)
                )
                if not self.cache_manager.get_cached_chatters():
                    await self.cache_manager._update_chatters_cache(ctx.channel, self.bot.nick)

            cached_chatters = self.cache_manager.get_cached_chatters()
            if not cached_chatters:
                self.logger.warning("🚫 Нет подходящих пользователей для команды 'дрын'")
                return

            target_chatter = random.choice(cached_chatters)
            target_id = await self.user_manager.get_user_id(target_chatter.name, target_chatter)

            if not target_id:
                self.logger.error(f"❌ Не удалось получить ID пользователя: {target_chatter.name}")
                return

            # Параллельное выполнение
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
                self.update_cooldown("club")  # Обновляем кулдаун только при успехе
                self.logger.info(f"🪵 Дрын применён к {target_chatter.name}")
                asyncio.create_task(
                    self.cache_manager._update_chatters_cache(ctx.channel, self.bot.nick)
                )
            else:
                # Если таймаут не удался, не обновляем кулдаун
                self.logger.warning(f"⚠️ Таймаут не удался: {status}")

        except Exception as e:
            self.logger.error(f"🚨 Ошибка команды 'дрын': {e}")
        finally:
            execution_time = (time.time() - start_time) * 1000
            if execution_time > 500:
                self.logger.info(f"⏱️ Время выполнения !дрын: {execution_time:.2f}ms")

    async def handle_butt_command(self, ctx) -> None:
        """Обработка команды !жопа"""
        start_time = time.time()
        try:
            # Проверяем кулдаун команды
            if not self.check_cooldown("butt"):
                return

            random_chance = random.randint(1, 100)
            privileged = is_privileged(ctx.author)

            if random_chance < 90:
                message = f"Жопа @{ctx.author.name} воняет на {random_chance}% xdding"
                await ctx.send(message)
                self.update_cooldown("butt")  # Обновляем кулдаун
                return

            # Специальные случаи
            duration = 600 if random_chance == 100 else 60
            reason = "extreme жопа" if random_chance == 100 else "жопа"
            message = (
                f"Жопа @{ctx.author.name} воняет на все 100% xdding 👑 Амбассадор вони! "
                f"Отправлен в мойку на {format_duration(duration)} washing"
                if random_chance == 100 else
                f"Жопа @{ctx.author.name} воняет на {random_chance}% xdding "
                f"Отправлен в мойку на {format_duration(duration)} washing"
            )

            if privileged:
                await ctx.send(message + " ТАКИЕ ТВОИ МОДЕРЫ ХУЕГЛОТАЛКИ GAGAGA")
                self.logger.info(f"🛡️ Модератор избежал наказания: {ctx.author.name}")
                self.update_cooldown("butt")  # Обновляем кулдаун даже для модераторов
            else:
                target_id = await self.user_manager.get_user_id(ctx.author.name, ctx.author)
                if not target_id:
                    self.logger.error(f"❌ Не удалось получить ID пользователя: {ctx.author.name}")
                    return

                status, response = await self.api.timeout_user(
                    user_id=target_id,
                    channel_name=ctx.channel.name,
                    duration=duration,
                    reason=reason,
                )

                if status == 200:
                    await ctx.send(message)
                    self.update_cooldown("butt")  # Обновляем кулдаун при успехе
                else:
                    # Если таймаут не удался, не обновляем кулдаун
                    self.logger.warning(f"⚠️ Таймаут не удался: {status}")

        except Exception as e:
            self.logger.error(f"🚨 Ошибка команды 'жопа': {e}")
        finally:
            execution_time = (time.time() - start_time) * 1000
            if execution_time > 500:
                self.logger.info(f"⏱️ Время выполнения !жопа: {execution_time:.2f}ms")

    async def handle_test_barrel_command(self, ctx) -> None:
        """Обработка команды !тестовая_бочка"""
        start_time = time.time()
        try:
            # Проверяем права администратора
            if ctx.author.name.lower() not in self.bot.config.get("admins", []):
                self.logger.warning(f"Попытка бочки от неавторизованного пользователя: {ctx.author.name}")
                return

            # Проверяем кулдаун команды
            if not self.check_cooldown("test_barrel"):
                return

            valid_chatters = self.cache_manager._filter_chatters(ctx.channel.chatters)
            if not valid_chatters:
                self.logger.warning("🚫 Нет подходящих пользователей для команды 'бочка'")
                return

            selected_count = min(10, len(valid_chatters))
            targets = random.sample(valid_chatters, selected_count)

            # Параллельное выполнение
            timeout_tasks = []
            for target in targets:
                target_id = await self.user_manager.get_user_id(target.name, target)
                if target_id:
                    timeout_tasks.append(
                        self.api.timeout_user(
                            user_id=target_id,
                            channel_name=ctx.channel.name,
                            duration=15,
                            reason="Тестовая бочка"
                        )
                    )

            if not timeout_tasks:
                self.logger.error("❌ Не удалось получить ID пользователей")
                return

            results = await asyncio.gather(*timeout_tasks, return_exceptions=True)
            punished_users = []

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"🚨 Ошибка при обработке {targets[i].name}: {result}")
                    continue

                status, response = result
                if status == 200:
                    punished_users.append(targets[i].name)

            if punished_users:
                names_list = ", ".join(f"@{name}" for name in punished_users)
                message = f"{ctx.author.name} Тест. По пиздаку получили: {names_list}"
            else:
                message = f"{ctx.author.name} Тест. Бочка дала осечку!"

            await ctx.send(message)
            self.update_cooldown("test_barrel")  # Обновляем кулдаун
            self.logger.info(f"✅ Тестовая бочка завершена. Успешно: {len(punished_users)}")

        except Exception as e:
            self.logger.error(f"💥 Критическая ошибка в 'тестовая бочка': {e}")
        finally:
            execution_time = (time.time() - start_time) * 1000
            if execution_time > 500:
                self.logger.info(f"⏱️ Время выполнения !тестовая_бочка: {execution_time:.2f}ms")

    async def handle_command(self, ctx) -> None:
        """Не используется для простых команд"""
        pass