from typing import Optional


class UserManager:
    """
    Manager for user-related operations.

    Handles user ID retrieval with caching and fallback strategies
    to optimize performance and reduce API calls.
    """

    def __init__(self, bot, cache_manager):
        self.bot = bot
        self.cache_manager = cache_manager

    async def get_user_id(self, username: str, user_obj=None) -> Optional[str]:
        """
        Retrieve user ID using optimal strategy with caching.

        Args:
            username: Twitch username to look up
            user_obj: Optional user object with ID attribute

        Returns:
            User ID string if found, None otherwise
        """
        cached_id = self.cache_manager.user_id_cache.get(username)
        if cached_id:
            return cached_id

        if user_obj and hasattr(user_obj, 'id') and user_obj.id:
            self.cache_manager.user_id_cache.set(username, user_obj.id)
            return user_obj.id

        try:
            user_data = await self.bot.fetch_users(names=[username])
            if user_data and user_data[0].id:
                self.cache_manager.user_id_cache.set(username, user_data[0].id)
                return user_data[0].id
        except Exception as e:
            print(f"Error retrieving ID for {username}: {e}")

        return None
