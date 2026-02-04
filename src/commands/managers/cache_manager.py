import asyncio
import json
import logging
from dataclasses import asdict
from typing import Any

from redis.asyncio import Redis

from src.api.twitch_api import TwitchAPI
from src.commands.models.chatters import ChatterData


class CacheManager:
    """
    Central cache manager for command handlers.

    Handles caching of:
    - User cooldowns
    - Command cooldowns
    - Channel chatters
    """

    def __init__(self, redis: Redis) -> None:
        """Initialize the CacheManager with a Redis instance."""
        self.redis = redis
        self.logger = logging.getLogger(__name__)
        self._lock = asyncio.Lock()

    async def update_user_cooldown(self, user_id: str, cooldown: int = 30) -> None:
        """
        Set a cooldown for a user.

        Args:
            user_id: ID of the user.
            cooldown: Cooldown duration in seconds.
        """
        try:
            await self.redis.setex(f"bot:user_cd:{user_id}", cooldown, "1")
        except Exception as e:
            self.logger.warning(f"Failed to set cooldown for user {user_id}: {e}")

    async def can_user_participate(self, user_id: str) -> bool:
        """
        Check if a user is allowed to participate (not on cooldown).

        Args:
            user_id: ID of the user.

        Returns:
            True if the user can participate, False if on cooldown.
        """
        try:
            exists: int = await self.redis.exists(f"bot:user_cd:{user_id}")
            return exists == 0
        except Exception as e:
            self.logger.warning(f"Failed to check cooldown for user {user_id}: {e}")
            return True

    async def set_command_cooldown(self, command: str, duration: int) -> None:
        """
        Set a cooldown for a command.

        Args:
            command: Name of the command.
            duration: Cooldown duration in seconds.
        """
        try:
            await self.redis.setex(f"bot:cmd_cd:{command.lower()}", duration, "1")
        except Exception as e:
            self.logger.warning(f"Failed to set cooldown for command '{command}': {e}")

    async def get_command_cooldown(self, command: str) -> bool:
        """
        Check if a command is available (not on cooldown).

        Args:
            command: Name of the command.

        Returns:
            True if the command is available, False if on cooldown.
        """
        try:
            exists: int = await self.redis.exists(f"bot:cmd_cd:{command.lower()}")
            return exists == 0
        except Exception as e:
            self.logger.warning(f"Failed to check cooldown for command '{command}': {e}")
            return True

    async def get_or_update_chatters(self, channel_name: str, api: TwitchAPI) -> list[ChatterData]:
        """
        Retrieve cached chatters for a channel, or fetch from API if not cached.

        Args:
            channel_name: Name of the Twitch channel.
            api: Twitch API client instance.

        Returns:
            List of ChatterData objects.
        """
        cached = await self.get_cached_chatters(channel_name)
        if cached:
            return cached

        api_chatters = await api.get_chatters(channel_name)
        normalized = [self._normalize_chatter(c) for c in api_chatters]
        await self.update_chatters_cache(channel_name, normalized)
        return normalized

    async def get_cached_chatters(self, channel_name: str) -> list[ChatterData]:
        """
        Get chatters from Redis cache.

        Args:
            channel_name: Name of the Twitch channel.

        Returns:
            List of ChatterData if cache exists, else empty list.
        """
        key = f"bot:chatters:{channel_name.lower()}"
        val = await self.redis.get(key)
        if val:
            try:
                data = json.loads(val)
                return [ChatterData(**c) for c in data]
            except (json.JSONDecodeError, TypeError) as e:
                self.logger.warning(f"Failed to load chatter cache for channel '{channel_name}': {e}")
        return []

    async def update_chatters_cache(self, channel_name: str, chatters: list[ChatterData], ttl: int = 300) -> None:
        """
        Update the Redis cache with the list of chatters.

        Args:
            channel_name: Name of the Twitch channel.
            chatters: List of ChatterData to cache.
            ttl: Time to live in seconds for the cache (default 300 seconds).
        """
        key = f"bot:chatters:{channel_name.lower()}"
        try:
            await self.redis.setex(key, ttl, json.dumps([asdict(c) for c in chatters]))
        except Exception as e:
            self.logger.warning(f"Failed to update chatter cache for channel '{channel_name}': {e}")

    async def get_user_id(self, username: str, channel_name: str, api: TwitchAPI) -> str | None:
        """
        Get a user's Twitch ID using the cached chatters, fallback to API if missing.

        Args:
            username: Username to look up.
            channel_name: Twitch channel name.
            api: Twitch API client.

        Returns:
            User ID as string if found, else None.
        """
        username_lower = username.lower()
        chatters: list[ChatterData] = await self.get_or_update_chatters(channel_name, api)

        for chatter in chatters:
            if chatter.name.lower() == username_lower:
                return chatter.id if chatter.id else None

        self.logger.warning(f"User '{username}' not found in chatters for channel '{channel_name}'")
        return None

    @staticmethod
    def _normalize_chatter(c: Any) -> ChatterData:
        """
        Normalize a raw Twitch API object or dict to a ChatterData instance.

        Args:
            c: Raw Twitch user object or dict.

        Returns:
            ChatterData object.
        """
        if hasattr(c, "id") and hasattr(c, "name"):
            return ChatterData(
                id=str(c.id),
                name=c.name,
                display_name=getattr(c, "display_name", c.name),
            )
        elif isinstance(c, dict):
            return ChatterData(
                id=str(c.get("user_id", "")),
                name=c.get("user_name", ""),
                display_name=c.get("user_name", ""),
            )
        else:
            return ChatterData(id="", name=str(c), display_name=str(c))
