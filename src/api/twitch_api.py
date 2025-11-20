import logging
from typing import Optional, Tuple

import aiohttp


class TwitchAPI:
    """
    Twitch API client for handling HTTP requests to Twitch Helix API.

    Manages API sessions, authentication headers, and provides methods
    for common Twitch API operations like user timeouts.
    """

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

    async def _ensure_session(self) -> None:
        """Initialize aiohttp session if not already created."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            self.logger.info("aiohttp session created")

    async def refresh_headers(self) -> None:
        """Refresh authentication headers with current token."""
        try:
            await self._ensure_session()
            self.headers = {
                "Authorization": f"Bearer {self.bot.token_manager.token}",
                "Client-Id": self.bot.token_manager.client_id,
                "Content-Type": "application/json"
            }
            token_part = self.bot.token_manager.token
            masked_token = f"{token_part[:5]}...{token_part[-5:]}" if token_part else "empty"
            self.logger.info(f"TwitchAPI headers refreshed. Token: {masked_token}")
        except Exception as e:
            self.logger.error(f"Error refreshing headers: {e}")
            self.session = None
            await self._ensure_session()

    async def timeout_user(self, user_id: str, channel_name: str, duration: int, reason: str) -> Tuple[int, str]:
        """
        Issue timeout to a user in specified channel.

        Args:
            user_id: Target user ID
            channel_name: Channel name where timeout should be applied
            duration: Timeout duration in seconds
            reason: Reason for the timeout

        Returns:
            Tuple of (status_code, response_data)
        """
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
            self.logger.error(f"API timeout error: {e}")
            return 0, str(e)

    async def _get_user_id(self, username: str) -> Optional[str]:
        """
        Get user ID by username.

        Args:
            username: Twitch username to look up

        Returns:
            User ID string if found, None otherwise
        """
        await self._ensure_session()

        url = f"{self.base_url}/users"
        params = {"login": username}

        try:
            async with self.session.get(url, params=params, headers=self.headers) as response:
                data = await response.json()
                return data["data"][0]["id"] if data.get("data") else None
        except Exception as e:
            self.logger.error(f"Error getting user ID for {username}: {e}")
            return None

    async def close(self) -> None:
        """Close aiohttp session on shutdown."""
        if self.session and not self.session.closed:
            try:
                await self.session.close()
                self.logger.info("aiohttp session closed")
            except Exception as e:
                self.logger.error(f"Error closing session: {e}")
        elif self.session:
            self.logger.debug("Session already closed")
        else:
            self.logger.debug("Session was never created")
