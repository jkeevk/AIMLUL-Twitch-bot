from typing import Any, Protocol

from src.commands.managers.cache_manager import CacheManager


class HasID(Protocol):
    id: str


class UserManager:
    """
    Manager for user-related operations.

    Handles user ID retrieval with caching and fallback strategies
    to optimize performance and reduce API calls.
    """

    bot: Any
    cache_manager: CacheManager

    def __init__(self, bot: Any, cache_manager: CacheManager) -> None:
        self.bot = bot
        self.cache_manager = cache_manager

    async def get_user_id(self, username: str, user_obj: HasID | None = None) -> str | None:
        """
        Retrieve user ID using optimal strategy with caching.

        Args:
            username: Twitch username to look up
            user_obj: Optional user object with ID attribute

        Returns:
            User ID string if found, None otherwise
        """
        cached_id = self.cache_manager.user_id_cache.get(username)
        if cached_id is not None:
            return cached_id

        if user_obj and hasattr(user_obj, "id") and user_obj.id:
            self.cache_manager.user_id_cache.set(username, str(user_obj.id))
            return str(user_obj.id)

        try:
            user_data: list[HasID] = await self.bot.fetch_users(names=[username])
            if user_data and user_data[0].id:
                self.cache_manager.user_id_cache.set(username, str(user_data[0].id))
                return str(user_data[0].id)
        except Exception as e:
            print(f"Error retrieving ID for {username}: {e}")

        return None
