import aiohttp
import configparser
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TokenManager:
    """
    Manager for Twitch OAuth token operations.

    Handles token validation, refresh, and persistence for Twitch API authentication.
    """

    def __init__(self, config_path: str):
        """
        Initialize TokenManager with configuration.

        Args:
            config_path: Path to configuration file containing token data
        """
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self.config.read(config_path)

        self._token = self.config.get("TOKEN", "token", fallback=None)
        self.client_id = self.config.get("TOKEN", "client_id")
        self.client_secret = self.config.get("TOKEN", "client_secret")
        self.refresh_token = self.config.get("TOKEN", "refresh_token")
        self.scope = self.config.get("TOKEN", "scope", fallback="")

    @property
    def token(self) -> Optional[str]:
        """Get current access token."""
        return self._token

    def _save(self) -> None:
        """Save current token state to configuration file."""
        with open(self.config_path, "w") as f:
            self.config.write(f)

    async def validate_token(self, token: str) -> bool:
        """
        Validate token with Twitch OAuth validation endpoint.

        Args:
            token: Access token to validate

        Returns:
            True if token is valid, False otherwise
        """
        url = "https://id.twitch.tv/oauth2/validate"
        headers = {"Authorization": f"OAuth {token}"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Token valid. Scopes: {data.get('scopes', [])}")
                        return True
                    return False
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return False

    async def refresh_access_token(self) -> str:
        """
        Refresh access token using refresh token.

        Returns:
            New access token string

        Raises:
            RuntimeError: If token refresh fails
        """
        logger.info("Refreshing access token...")

        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params) as response:
                    data = await response.json()

                    if response.status != 200:
                        raise RuntimeError(f"Token refresh failed: {response.status} {data}")

                    new_token = data["access_token"]
                    new_refresh = data.get("refresh_token", self.refresh_token)

                    self._token = new_token
                    self.refresh_token = new_refresh

                    self.config.set("TOKEN", "token", new_token)
                    self.config.set("TOKEN", "refresh_token", new_refresh)
                    self._save()

                    logger.info(f"Token refreshed successfully")
                    return new_token

        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            raise

    async def get_access_token(self) -> str:
        """
        Get valid access token, refreshing if necessary.

        Returns:
            Valid access token string
        """
        if not self.token:
            return await self.refresh_access_token()

        if await self.validate_token(self.token):
            return self.token

        return await self.refresh_access_token()
