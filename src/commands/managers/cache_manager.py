import asyncio
import logging
import time
from typing import Any

from twitchio import Chatter, PartialUser

from src.commands.permissions import is_privileged


class UserIDCache:
    """
    Cache for storing user ID mappings with TTL and size limits.

    Provides efficient storage and retrieval of username to user ID mappings
    with automatic cleanup of expired entries.
    """

    def __init__(self, max_size: int = 1000, ttl: int = 3600) -> None:
        """
        Initialize the UserIDCache.

        Args:
            max_size: Maximum number of entries in the cache.
            ttl: Time-to-live for cache entries in seconds.
        """
        self._cache: dict[str, tuple[str, float]] = {}
        self._max_size: int = max_size
        self._ttl: int = ttl

    def get(self, username: str) -> str | None:
        """
        Retrieve user ID from cache.

        Args:
            username: Username to look up

        Returns:
            User ID if found and not expired, None otherwise
        """
        if username in self._cache:
            user_id, timestamp = self._cache[username]
            if time.time() - timestamp < self._ttl:
                return user_id
            del self._cache[username]
        return None

    def set(self, username: str, user_id: str) -> None:
        """
        Store user ID in cache.

        Args:
            username: Username to store
            user_id: Corresponding user ID
        """
        if len(self._cache) >= self._max_size:
            self._cleanup()
        self._cache[username] = (user_id, time.time())

    def _cleanup(self) -> None:
        """Remove oldest entries when cache exceeds maximum size."""
        if len(self._cache) >= self._max_size:
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1][1])
            remove_count = max(1, len(sorted_items) // 10)
            for key, _ in sorted_items[:remove_count]:
                del self._cache[key]


class CacheManager:
    """
    Central cache manager for command handlers.

    Manages various caches including user IDs, chatters list,
    and cooldowns for commands and users.
    """

    def __init__(self) -> None:
        """Initialize the CacheManager."""
        self._cached_chatters: list[Any] = []
        self._last_cache_update: float = 0
        self._cache_ttl: int = 300
        self.bot_nick: str = ""
        self._cache_lock: asyncio.Lock = asyncio.Lock()
        self.user_id_cache: UserIDCache = UserIDCache()
        self._user_cooldowns: dict[str, float] = {}
        self.command_cooldowns: dict[str, int] = {}
        self.logger = logging.getLogger(__name__)

    def _is_valid_target(self, chatter: Any) -> bool:
        """
        Check if user is valid target for timeout actions.

        Args:
            chatter: User object to validate

        Returns:
            True if user can be targeted, False otherwise
        """
        if hasattr(chatter, "name") and chatter.name.lower() == self.bot_nick.lower():
            return False
        if isinstance(chatter, PartialUser):
            return True
        if isinstance(chatter, Chatter):
            return not is_privileged(chatter)
        return False

    def filter_chatters(self, chatters: list[Any]) -> list[Any]:
        """
        Filter chatters list to valid targets.

        Args:
            chatters: List of chatter objects

        Returns:
            Filtered list of valid targets
        """
        return [chatter for chatter in chatters if self._is_valid_target(chatter)]

    async def update_chatters_cache(self, channel: Any, bot_nick: str) -> None:
        """
        Update the cached list of chatters for a channel.

        Args:
            channel: Twitch channel object containing `.chatters`.
            bot_nick: Bot's username to exclude from cache.
        """
        async with self._cache_lock:
            try:
                self.bot_nick = bot_nick
                self._cached_chatters = self.filter_chatters(channel.chatters)
                self._last_cache_update = time.time()
            except Exception as e:
                self.logger.error("Cache update error", exc_info=e)

    def get_cached_chatters(self) -> list[Any]:
        """
        Get cached chatters list.

        Returns:
            List of cached chatter objects
        """
        return self._cached_chatters

    def should_update_cache(self) -> bool:
        """
        Check if cache needs updating.

        Returns:
            True if cache is empty or expired, False otherwise
        """
        return not self._cached_chatters or (time.time() - self._last_cache_update > self._cache_ttl)

    def update_user_cooldown(self, user_id: str) -> None:
        """
        Update user participation cooldown.

        Args:
            user_id: User ID to update cooldown for
        """
        self._user_cooldowns[user_id] = time.time()

    def can_user_participate(self, user_id: str, cooldown: int = 30) -> bool:
        """
        Check if user can participate based on cooldown.

        Args:
            user_id: User ID to check
            cooldown: Cooldown duration in seconds

        Returns:
            True if user can participate, False if on cooldown
        """
        last_time = self._user_cooldowns.get(user_id, 0)
        return (time.time() - last_time) >= cooldown
