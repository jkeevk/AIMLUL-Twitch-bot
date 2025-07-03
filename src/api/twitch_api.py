import logging
from typing import Optional

import aiohttp


class TwitchAPI:
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.base_url = "https://api.twitch.tv/helix"
        self.session = None
        self.headers = {
            "Authorization": f"Bearer {self.bot.token_manager.token}",
            "Client-Id": self.bot.token_manager.client_id,
            "Content-Type": "application/json"
        }

    async def _ensure_session(self):
        """Создает сессию при первом использовании"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            self.logger.info("🌐 Сессия aiohttp создана")

    async def refresh_headers(self):
        try:
            await self._ensure_session()
            self.headers = {
                "Authorization": f"Bearer {self.bot.token_manager.token}",
                "Client-Id": self.bot.token_manager.client_id,
                "Content-Type": "application/json"
            }
            token_part = self.bot.token_manager.token
            masked_token = f"{token_part[:5]}...{token_part[-5:]}" if token_part else "empty"
            self.logger.info(f"🔄 Заголовки TwitchAPI обновлены. Токен: {masked_token}")
        except Exception as e:
            self.logger.error(f"🚨 Ошибка обновления заголовков: {e}")
            self.session = None
            await self._ensure_session()

    async def timeout_user(self, user_id: str, channel_name: str, duration: int, reason: str) -> tuple:
        """Выдает таймаут пользователю"""
        await self._ensure_session()
        broadcaster_id = await self._get_user_id(channel_name)
        if not broadcaster_id:
            return 0, "Broadcaster not found"

        url = f"{self.base_url}/moderation/bans"
        params = {
            "broadcaster_id": broadcaster_id,
            "moderator_id": self.bot.user_id
        }
        data = {
            "data": {
                "user_id": user_id,
                "duration": duration,
                "reason": reason
            }
        }

        try:
            async with self.session.post(url, params=params, json=data, headers=self.headers) as response:
                return response.status, await response.json()
        except Exception as e:
            self.logger.error(f"API Error: {e}")
            return 0, str(e)

    async def _get_user_id(self, username: str) -> Optional[str]:
        """Получает ID пользователя по имени"""
        await self._ensure_session()

        url = f"{self.base_url}/users"
        params = {"login": username}

        try:
            async with self.session.get(url, params=params, headers=self.headers) as response:
                data = await response.json()
                return data["data"][0]["id"] if data.get("data") else None
        except Exception as e:
            self.logger.error(f"Ошибка получения ID для {username}: {e}")
            return None

    async def close(self):
        """Закрывает сессию при завершении"""
        if self.session and not self.session.closed:
            try:
                await self.session.close()
                self.logger.info("🔌 Сессия aiohttp закрыта")
            except Exception as e:
                self.logger.error(f"🚨 Ошибка при закрытии сессии: {e}")
        elif self.session:
            self.logger.debug("Сессия уже закрыта")
        else:
            self.logger.debug("Сессия никогда не создавалась")
