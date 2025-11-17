from typing import Optional


class UserManager:
    """Менеджер для работы с пользователями"""

    def __init__(self, bot, cache_manager):
        self.bot = bot
        self.cache_manager = cache_manager

    async def get_user_id(self, username: str, user_obj=None) -> Optional[str]:
        """Получает ID пользователя оптимальным способом"""
        # Пробуем получить из кэша
        cached_id = self.cache_manager.user_id_cache.get(username)
        if cached_id:
            return cached_id

        # Пробуем получить из объекта
        if user_obj and hasattr(user_obj, 'id') and user_obj.id:
            self.cache_manager.user_id_cache.set(username, user_obj.id)
            return user_obj.id

        # Fallback: запрос к API
        try:
            user_data = await self.bot.fetch_users(names=[username])
            if user_data and user_data[0].id:
                self.cache_manager.user_id_cache.set(username, user_data[0].id)
                return user_data[0].id
        except Exception as e:
            print(f"❌ Ошибка получения ID для {username}: {e}")

        return None