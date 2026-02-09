import logging
from json import JSONDecodeError
from typing import Any, cast

import aiohttp
from aiohttp import ClientSession


class TwitchAPI:
    """
    Twitch API client for handling HTTP requests to the Twitch Helix API.

    Manages API sessions, authentication headers, and provides methods
    for common Twitch API operations, such as user timeouts.
    """

    BROADCASTER_TTL = 86400

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
        """
        Construct and return the current headers for API requests.

        Returns:
            Dictionary of headers for Twitch API requests.
        """
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
            self.session = ClientSession(timeout=timeout, connector=connector)
            self.logger.info("aiohttp session created")

    async def refresh_headers(self) -> None:
        """Refresh authentication headers with the current bot token."""
        await self._ensure_session()
        self.headers = self.get_headers()
        bot_token = self.bot_token()
        masked_token = f"{bot_token[:5]}...{bot_token[-5:]}" if bot_token else "empty"
        self.logger.info(f"TwitchAPI headers refreshed. Token: {masked_token}")

    async def _request_with_token_refresh(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> tuple[int, dict[str, Any]]:
        """
        Internal request helper that handles 401 Unauthorized by refreshing the bot token once.

        Args:
            method: HTTP method ('get', 'post', etc.)
            url: Full URL
            kwargs: aiohttp request parameters (headers, params, JSON, etc.)

        Returns:
            Tuple of (status_code, json_data)
        """
        await self._ensure_session()
        session = cast(ClientSession, self.session)

        async def do_request() -> tuple[int, dict[str, Any]]:
            async with session.request(method, url, **kwargs) as resp:
                try:
                    resp_data: dict[str, Any] = await resp.json()
                except JSONDecodeError:
                    resp_data = {}
                return resp.status, resp_data

        status, data = await do_request()

        if status == 401:
            self.logger.warning("Bot token expired, refreshing...")
            await self.bot.token_manager.refresh_access_token("BOT_TOKEN")
            await self.refresh_headers()
            kwargs["headers"] = self.headers
            status, data = await do_request()

        return status, data

    async def get_chatters(self, channel_name: str, broadcaster_id: str | None = None) -> list[dict[str, str]]:
        """
        Get the list of chatters using Twitch Helix API.

        Args:
            channel_name: The name of the channel to get chatters for.
            broadcaster_id: Twitch channel ID.

        Returns:
            List of dicts with user info: [{"user_name": "...", "user_id": "..."}]
        """
        await self._ensure_session()
        if not broadcaster_id:
            broadcaster_id = await self.get_broadcaster_id(channel_name)

        if not broadcaster_id:
            self.logger.warning(f"Broadcaster not found: {channel_name}")
            return []

        url = f"{self.base_url}/chat/chatters"
        params = {"broadcaster_id": broadcaster_id, "moderator_id": self.bot.user_id, "first": 1000}

        status, data = await self._request_with_token_refresh("get", url, params=params, headers=self.headers)

        if status != 200:
            self.logger.error(f"Failed to fetch chatters: {status} {data}")
            return []

        raw_chatters = data.get("data", [])
        return [{"user_name": c["user_name"], "user_id": c["user_id"]} for c in raw_chatters]

    async def get_broadcaster_id(self, channel_name: str) -> str | None:
        """
        Retrieve broadcaster ID from Redis cache.

        If not found in cache, fetch from Twitch API and store in Redis.

        Args:
            channel_name: Name of the Twitch channel

        Returns:
            Broadcaster ID as a string, or None if not found
        """
        cached_id = await self.bot.cache_manager.redis.get(f"bot:broadcaster_id:{channel_name.lower()}")
        if cached_id:
            return str(cached_id)

        user_id = await self._get_user_id(channel_name)
        if user_id:
            await self.bot.cache_manager.redis.setex(
                f"bot:broadcaster_id:{channel_name.lower()}", self.BROADCASTER_TTL, user_id
            )
        return user_id

    async def timeout_user(
        self,
        user_id: str,
        channel_name: str,
        duration: int,
        reason: str,
    ) -> tuple[int, Any]:
        """
        Issue timeout to a user in the specified channel.

        Args:
            user_id: Target user ID
            channel_name: Channel name where timeout should be applied
            duration: Timeout duration in seconds
            reason: Reason for the timeout

        Returns:
            Tuple of (status_code, response_data)
        """
        await self._ensure_session()

        broadcaster_id = await self.get_broadcaster_id(channel_name)

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

        status, resp_json = await self._request_with_token_refresh(
            "post", url, params=params, json=data, headers=self.headers
        )

        if status >= 400:
            self.logger.warning(f"Timeout API returned {status}: {resp_json}")

        return status, resp_json

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

        status, data = await self._request_with_token_refresh("get", url, params=params, headers=self.headers)

        users = data.get("data", [])
        if users and isinstance(users[0], dict) and "id" in users[0]:
            return cast(str, users[0]["id"])
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
