import logging
from typing import Any, cast

import aiohttp
from aiohttp import ClientSession


class TwitchAPI:
    """
    Twitch API client for handling HTTP requests to the Twitch Helix API.

    Manages API sessions, authentication headers, and provides methods
    for common Twitch API operations, such as user timeouts.
    """

    def __init__(self, bot: Any) -> None:
        """
        Initialize TwitchAPI client.

        Args:
            bot: Instance of the TwitchBot containing token_manager and user_id.
        """
        self.bot: Any = bot
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.base_url: str = "https://api.twitch.tv/helix"
        self.session: ClientSession | None = None
        self.headers: dict[str, str] = self.get_headers()

    def bot_token(self) -> str:
        """
        Retrieve the current bot access token.

        Raises:
            RuntimeError: If the bot token is missing.

        Returns:
            Current bot access token string.
        """
        token: str = self.bot.token_manager.tokens["BOT_TOKEN"].access_token
        if not token:
            raise RuntimeError("BOT_TOKEN is missing!")
        return token

    def get_headers(self) -> dict[str, str]:
        """Construct and return the current headers for API requests."""
        bot_token = self.bot_token()
        return {
            "Authorization": f"Bearer {bot_token}",
            "Client-Id": self.bot.token_manager.tokens["BOT_TOKEN"].client_id,
            "Content-Type": "application/json",
        }

    async def _ensure_session(self) -> None:
        """Ensure that an aiohttp session exists and is open."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            connector = aiohttp.TCPConnector(limit=10)
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            self.logger.info("aiohttp session created")

    async def refresh_headers(self) -> None:
        """Refresh authentication headers with the current bot token."""
        await self._ensure_session()
        self.headers = self.get_headers()
        bot_token = self.bot_token()
        masked_token = f"{bot_token[:5]}...{bot_token[-5:]}" if bot_token else "empty"
        self.logger.info(f"TwitchAPI headers refreshed. Token: {masked_token}")

    async def get_chatters(self, channel_name: str, broadcaster_id: str | None = None) -> list[dict[str, str]]:
        """
        Get list of chatters using Twitch Helix API.

        Args:
            channel_name: The name of the channel to get chatters for.
            broadcaster_id: Twitch channel ID.

        Returns:
            List of dicts with user info: [{"user_name": "...", "user_id": "..."}]
        """
        await self._ensure_session()
        if not broadcaster_id:
            broadcaster_id = await self._get_user_id(channel_name)

        if not broadcaster_id:
            self.logger.warning(f"Broadcaster not found: {channel_name}")
            return []

        url = f"{self.base_url}/chat/chatters"
        params = {
            "broadcaster_id": broadcaster_id,
            "moderator_id": self.bot.user_id,
        }

        headers = {
            "Authorization": f"Bearer {self.bot_token()}",
            "Client-ID": self.bot.token_manager.tokens["BOT_TOKEN"].client_id,
        }

        assert self.session is not None
        try:
            async with self.session.get(url, params=params, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    self.logger.error(f"Failed to fetch chatters: {resp.status} {text}")
                    return []

                data = await resp.json()
                raw_chatters = data.get("data", [])
                return [{"user_name": c["user_name"], "user_id": c["user_id"]} for c in raw_chatters]
        except Exception as e:
            self.logger.error(f"Error fetching chatters: {e}", exc_info=True)
            return []

    async def timeout_user(self, user_id: str, channel_name: str, duration: int, reason: str) -> tuple[int, Any]:
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
            "moderator_id": self.bot.user_id,
        }
        data = {
            "data": {
                "user_id": user_id,
                "duration": duration,
                "reason": reason,
            }
        }

        assert self.session is not None
        try:
            async with self.session.post(url, params=params, json=data, headers=self.headers) as response:
                resp_json = await response.json()
                if response.status >= 400:
                    self.logger.warning(f"Timeout API returned {response.status}: {resp_json}")
                return response.status, resp_json
        except Exception as e:
            self.logger.error(f"API timeout error: {e}", exc_info=True)
            return 0, str(e)

    async def _get_user_id(self, username: str) -> str | None:
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

        assert self.session is not None
        try:
            async with self.session.get(url, params=params, headers=self.headers) as response:
                data: dict[str, Any] = await response.json()
                users = data.get("data", [])
                if users and isinstance(users[0], dict) and "id" in users[0]:
                    return cast(str, users[0]["id"])
                return None
        except Exception as e:
            self.logger.error(f"Error getting user ID for {username}: {e}", exc_info=True)
            return None

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            try:
                await self.session.close()
                self.logger.info("aiohttp session closed")
            except Exception as e:
                self.logger.error(f"Error closing session: {e}", exc_info=True)
        elif self.session:
            self.logger.debug("Session already closed")
        else:
            self.logger.debug("Session was never created")
