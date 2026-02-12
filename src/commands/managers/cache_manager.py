import asyncio
import json
import logging
import time
from dataclasses import asdict
from typing import Any

from redis.asyncio import Redis

from src.api.twitch_api import TwitchAPI
from src.commands.models.chatters import ChatterData

USER_CD_KEY = "bot:user_cd:{}"
CMD_CD_KEY = "bot:cmd_cd:{}"
CHATTERS_KEY = "bot:chatters:{}"
ACTIVE_CHATTERS_KEY = "bot:active_chatters:{}"
ACTIVE_TTL = 900


class CacheManager:
    """
    Manages caching of Twitch bot data in Redis.

    Responsibilities:
        - User cooldowns
        - Command cooldowns
        - Channel chatters and active users
    """

    def __init__(self, redis: Redis) -> None:
        """
        Initialize CacheManager with a Redis client.

        Args:
            redis: Redis connection for caching bot data
        """
        self.redis = redis
        self.logger = logging.getLogger(__name__)
        self._lock = asyncio.Lock()

    async def update_user_cooldown(self, user_id: str, cooldown: int = 30) -> None:
        """
        Set a cooldown period for a user.

        Args:
            user_id: Twitch user ID
            cooldown: Duration of cooldown in seconds (default 30)
        """
        try:
            await self.redis.setex(USER_CD_KEY.format(user_id), cooldown, "1")
        except Exception as e:
            self.logger.warning(f"Failed to set cooldown for user {user_id}: {e}")

    async def can_user_participate(self, user_id: str) -> bool:
        """
        Check if a user is eligible to participate (not on cooldown).

        Args:
            user_id: Twitch user ID

        Returns:
            True if the user can participate, False if they are on cooldown
        """
        try:
            exists: int = await self.redis.exists(USER_CD_KEY.format(user_id))
            return exists == 0
        except Exception as e:
            self.logger.warning(f"Failed to check cooldown for user {user_id}: {e}")
            return True

    async def set_command_cooldown(self, command: str, duration: int) -> None:
        """
        Set a cooldown period for a command.

        Args:
            command: Name of the command
            duration: Cooldown duration in seconds
        """
        try:
            await self.redis.setex(
                CMD_CD_KEY.format(command.lower()),
                duration,
                "1",
            )
        except Exception as e:
            self.logger.warning(f"Failed to set cooldown for command '{command}': {e}")

    async def is_command_available(self, command: str) -> bool:
        """
        Check if a command is available to use (not on cooldown).

        Args:
            command: Name of the command

        Returns:
            True if the command is available, False if on cooldown
        """
        try:
            exists: int = await self.redis.exists(CMD_CD_KEY.format(command.lower()))
            return exists == 0
        except Exception as e:
            self.logger.warning(f"Failed to check cooldown for command '{command}': {e}")
            return True

    async def get_or_update_chatters(self, channel_name: str, api: TwitchAPI) -> list[ChatterData]:
        """
        Retrieve cached chatters or fetch them from the Twitch API if the cache is empty.

        Args:
                    channel_name: Name of the Twitch channel
                    api: Twitch API client

        Returns:
                    List of ChatterData objects representing channel chatters
        """
        cached = await self.get_cached_chatters(channel_name)
        if cached:
            return cached

        chatters = await self._fetch_and_cache_chatters(channel_name, api)
        return chatters

    async def get_cached_chatters(self, channel_name: str) -> list[ChatterData]:
        """
        Retrieve chatters from Redis cache for a given channel.

        Args:
            channel_name: Name of the Twitch channel

        Returns:
            List of ChatterData objects if cache exists, otherwise an empty list
        """
        key = CHATTERS_KEY.format(channel_name.lower())
        val = await self.redis.get(key)
        if val:
            try:
                data = json.loads(val)
                return [ChatterData(**c) for c in data]
            except (json.JSONDecodeError, TypeError) as e:
                self.logger.warning(f"Failed to load chatter cache for channel '{channel_name}': {e}")
        return []

    async def update_chatters_cache(self, channel_name: str, chatters: list[ChatterData], ttl: int = 1800) -> None:
        """
        Update the Redis cache with the provided list of chatters.

        Args:
            channel_name: Name of the Twitch channel
            chatters: List of ChatterData to cache
            ttl: Time-to-live for the cache in seconds (default 1800)
        """
        key = CHATTERS_KEY.format(channel_name.lower())
        try:
            await self.redis.setex(key, ttl, json.dumps([asdict(c) for c in chatters]))
        except Exception as e:
            self.logger.warning(f"Failed to update chatter cache for channel '{channel_name}': {e}")

    async def mark_user_active(self, channel_name: str, username: str, user_id: str) -> None:
        """
        Mark a user as active in a channel and maintain active users sorted set.

        Users inactive longer than ACTIVE_TTL seconds are removed.

        Args:
            channel_name: Twitch channel name
            username: Username to mark active
            user_id: Twitch user ID

        Returns:
            None
        """
        key = ACTIVE_CHATTERS_KEY.format(channel_name.lower())
        now = int(time.time())
        value = f"{username.lower()}:{user_id}"
        cutoff = now - ACTIVE_TTL

        try:
            await self.redis.zremrangebyscore(key, 0, cutoff)
            await self.redis.zadd(key, {value: now})
        except Exception as e:
            self.logger.warning(f"Failed to mark user active: {e}")

    async def get_active_chatters(self, channel_name: str) -> list[dict[str, str]]:
        """
        Retrieve a list of currently active chatters in a channel.

        Only users active within the last ACTIVE_TTL seconds are returned.

        Args:
            channel_name: Twitch channel name

        Returns:
            List of dicts with keys 'name' and 'id' representing active users
        """
        key = ACTIVE_CHATTERS_KEY.format(channel_name.lower())
        now = int(time.time())
        cutoff = now - ACTIVE_TTL

        try:
            raw_users = await self.redis.zrangebyscore(key, cutoff, now)
            users = []
            for u in raw_users:
                if isinstance(u, bytes):
                    u = u.decode()
                if ":" in u:
                    name, user_id = u.split(":", 1)
                    users.append({"name": name, "id": user_id})
            return users
        except Exception as e:
            self.logger.warning(f"Failed to get active chatters: {e}")
            return []

    async def get_user_id(self, username: str, channel_name: str, api: TwitchAPI) -> str | None:
        """
        Retrieve a user's Twitch ID using cached chatters, falling back to the API.

        Args:
            username: Twitch username
            channel_name: Twitch channel name
            api: Twitch API client

        Returns:
            User ID as a string if found, otherwise None
        """
        username_lower = username.lower()
        channel_lower = channel_name.lower()

        chatters: list[ChatterData] = await self.get_cached_chatters(channel_lower)

        user_id = self._find_user_id(chatters, username_lower)
        if user_id:
            return user_id

        async with self._lock:
            normalized = await self._fetch_and_cache_chatters(channel_lower, api)
            return self._find_user_id(normalized, username_lower)

    async def force_refresh_chatters(self, channel_name: str, api: TwitchAPI) -> list[ChatterData]:
        """
        Force fetch chatters from Twitch API and update the cache.

        Args:
            channel_name: Twitch channel name
            api: Twitch API client

        Returns:
            List of ChatterData objects representing channel chatters
        """
        try:
            self.logger.info(f"Forcing chatters refresh for channel '{channel_name}'")
            return await self._fetch_and_cache_chatters(channel_name, api)
        except Exception as e:
            self.logger.error(f"Failed to force refresh chatters for '{channel_name}': {e}")
            cached = await self.get_cached_chatters(channel_name)
            return cached if cached else []

    async def _fetch_and_cache_chatters(self, channel_name: str, api: TwitchAPI, ttl: int = 1800) -> list[ChatterData]:
        """
        Internal method to fetch chatters from Twitch API and cache them.

        Args:
            channel_name: Twitch channel name
            api: Twitch API client
            ttl: Cache time-to-live in seconds

        Returns:
            Normalized list of ChatterData objects
        """
        api_chatters = await api.get_chatters(channel_name)
        normalized = [self._normalize_chatter(c) for c in api_chatters]
        await self.update_chatters_cache(channel_name, normalized, ttl)
        return normalized

    @staticmethod
    def _normalize_chatter(c: Any) -> ChatterData:
        """
        Normalize a raw Twitch user object or dictionary into ChatterData.

        Args:
            c: Twitch API user object or dictionary

        Returns:
            ChatterData instance
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

    @staticmethod
    def _find_user_id(chatters: list[ChatterData], username_lower: str) -> str | None:
        """
        Search cached chatters for a specific user ID.

        Args:
            chatters: List of ChatterData objects
            username_lower: Lowercase username to search

        Returns:
            User ID as a string if found, otherwise None
        """
        for c in chatters:
            if c.name.lower() == username_lower:
                return c.id or None
        return None
