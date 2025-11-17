import time
import asyncio
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from twitchio import PartialUser, Chatter

from src.utils.helpers import is_privileged


class UserIDCache:
    """Кэш для ID пользователей"""

    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        self._cache: Dict[str, Tuple[str, float]] = {}
        self._max_size = max_size
        self._ttl = ttl

    def get(self, username: str) -> Optional[str]:
        if username in self._cache:
            user_id, timestamp = self._cache[username]
            if time.time() - timestamp < self._ttl:
                return user_id
            else:
                del self._cache[username]
        return None

    def set(self, username: str, user_id: str) -> None:
        if len(self._cache) >= self._max_size:
            self._cleanup()
        self._cache[username] = (user_id, time.time())

    def _cleanup(self) -> None:
        """Очищает старые записи при превышении лимита"""
        if len(self._cache) >= self._max_size:
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1][1])
            remove_count = max(1, len(sorted_items) // 10)
            for key, _ in sorted_items[:remove_count]:
                del self._cache[key]


class CacheManager:
    """Менеджер кэшей для команд"""

    def __init__(self):
        self._cached_chatters = []
        self._last_cache_update = 0
        self._cache_ttl = 300
        self._cache_lock = asyncio.Lock()
        self.user_id_cache = UserIDCache()
        self._user_cooldowns = {}
        self.command_cooldowns = defaultdict(int)

    def _is_valid_target(self, chatter) -> bool:
        """Проверяет, подходит ли пользователь для таймаута"""
        if hasattr(chatter, 'name') and chatter.name.lower() == getattr(self, 'bot_nick', '').lower():
            return False

        if isinstance(chatter, PartialUser):
            return True
        elif isinstance(chatter, Chatter):
            return not is_privileged(chatter)

        return False

    def _filter_chatters(self, chatters) -> List:
        """Фильтрует список чатеров"""
        return [chatter for chatter in chatters if self._is_valid_target(chatter)]

    async def _update_chatters_cache(self, channel, bot_nick: str) -> None:
        """Обновляет кэш списка чатеров"""
        async with self._cache_lock:
            try:
                self.bot_nick = bot_nick
                self._cached_chatters = self._filter_chatters(channel.chatters)
                self._last_cache_update = time.time()
            except Exception as e:
                print(f"🚨 Ошибка обновления кэша: {e}")

    def get_cached_chatters(self) -> List:
        """Возвращает кэшированных чатеров"""
        return self._cached_chatters

    def should_update_cache(self) -> bool:
        """Проверяет, нужно ли обновлять кэш"""
        return (not self._cached_chatters or
                time.time() - self._last_cache_update > self._cache_ttl)

    def update_user_cooldown(self, user_id: str) -> None:
        """Обновляет кулдаун пользователя"""
        self._user_cooldowns[user_id] = time.time()

    def can_user_participate(self, user_id: str, cooldown: int = 30) -> bool:
        """Проверяет, может ли пользователь участвовать"""
        if user_id in self._user_cooldowns:
            return time.time() - self._user_cooldowns[user_id] >= cooldown
        return True