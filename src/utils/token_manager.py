import configparser
import logging
import pathlib
from dataclasses import dataclass
from typing import Any

import aiohttp


@dataclass
class TokenData:
    """Container for token-related data."""

    access_token: str
    refresh_token: str
    client_id: str
    client_secret: str
    scope: str = ""


class TokenManager:
    """
    Manager for Twitch OAuth token operations with backward compatibility.

    Handles both bot token and streamer token with identical operations.
    """

    def __init__(self, config_path: str) -> None:
        """
        Initialize TokenManager with configuration.

        Args:
            config_path: Path to the configuration file containing token data
        """
        self.logger: logging.Logger = logging.getLogger(self.__class__.__name__)
        self.config_path: str = config_path
        self.config: configparser.ConfigParser = configparser.ConfigParser()
        self.config.read(config_path)

        self.tokens: dict[str, TokenData] = {}
        self._load_tokens()
        self.logger.info("TokenManager initialized")

    def _load_tokens(self) -> None:
        """Load all tokens from configuration with backward compatibility."""
        if self.config.has_section("BOT_TOKEN"):
            self._load_token_section("BOT_TOKEN")
        if self.config.has_section("STREAMER_TOKEN"):
            self._load_token_section("STREAMER_TOKEN")

    def _load_token_section(self, section: str, target_section: str | None = None) -> None:
        """Load token data from a specific config section."""
        target = target_section or section
        self.tokens[target] = TokenData(
            access_token=self.config.get(section, "token", fallback=""),
            refresh_token=self.config.get(section, "refresh_token", fallback=""),
            client_id=self.config.get(section, "client_id", fallback=""),
            client_secret=self.config.get(section, "client_secret", fallback=""),
            scope=self.config.get(section, "scope", fallback=""),
        )

    def _save_config(self) -> None:
        """Save the current token state to the configuration file."""
        for section, token_data in self.tokens.items():
            if not self.config.has_section(section):
                self.config.add_section(section)

            self.config.set(section, "token", token_data.access_token)
            self.config.set(section, "refresh_token", token_data.refresh_token)
            self.config.set(section, "client_id", token_data.client_id)
            self.config.set(section, "client_secret", token_data.client_secret)
            self.config.set(section, "scope", token_data.scope)

        with pathlib.Path(self.config_path).open("w") as f:
            self.config.write(f)
        self.logger.info("Configuration saved")

    async def validate_token(self, token: str) -> dict[str, Any] | None:
        """
        Validate token with Twitch OAuth validation endpoint.

        Args:
            token: Access token to validate

        Returns:
            dict with validation data (contains expires_in, client_id, scopes, etc.)
            or None if token is invalid
        """
        if not token:
            return None

        url = "https://id.twitch.tv/oauth2/validate"
        headers = {"Authorization": f"OAuth {token}"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data: dict[str, Any] = await response.json()
                        return data
                    return None
        except Exception as e:
            self.logger.error(f"Token validation error: {e}")
            return None

    async def refresh_access_token(self, token_type: str = "BOT_TOKEN") -> str:
        """
        Refresh access token using refresh token.

        Args:
            token_type: Type of token to refresh ("BOT_TOKEN" or "STREAMER_TOKEN")

        Returns:
            New access token string

        Raises:
            RuntimeError: If token refresh fails
            KeyError: If token type not found
        """
        if token_type not in self.tokens:
            raise KeyError(f"Token type '{token_type}' not found")

        token_data = self.tokens[token_type]

        if not token_data.refresh_token:
            raise RuntimeError(f"No refresh token available for {token_type}")

        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "grant_type": "refresh_token",
            "refresh_token": token_data.refresh_token,
            "client_id": token_data.client_id,
            "client_secret": token_data.client_secret,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params) as response:
                    data = await response.json()
                    if response.status != 200:
                        raise RuntimeError(f"Token refresh failed: {response.status} {data}")

                    token_data.access_token = data["access_token"]
                    token_data.refresh_token = data.get("refresh_token", token_data.refresh_token)

                    self._save_config()
                    self.logger.info(f"{token_type} refreshed successfully")
                    return token_data.access_token

        except Exception as e:
            self.logger.error(f"{token_type} refresh error: {e}", exc_info=True)
            raise

    async def get_access_token(self, token_type: str = "BOT_TOKEN") -> str:
        """
        Get valid access token, refreshing if necessary.

        Args:
            token_type: Type of token to get ("BOT_TOKEN" or "STREAMER_TOKEN")

        Returns:
            Valid access token string
        """
        if token_type not in self.tokens:
            raise KeyError(f"Token type '{token_type}' not found")

        token_data = self.tokens[token_type]
        if not token_data.access_token:
            return await self.refresh_access_token(token_type)

        info = await self.validate_token(token_data.access_token)

        if info is None:
            return await self.refresh_access_token(token_type)

        expires_in = info.get("expires_in", 1)
        token_display = (
            f"{token_data.access_token[:5]}...{token_data.access_token[-5:]}" if token_data.access_token else "empty"
        )
        self.logger.info(f"Access token <{token_display}> expires in {expires_in} seconds")

        refresh_in = 7200
        if self.config.has_section("SETTINGS"):
            refresh_in = self.config.getint("SETTINGS", "refresh_token_delay_time", fallback=7200)

        refresh_in += 10

        if expires_in < int(refresh_in):
            self.logger.warning(f"{token_type} expires in {expires_in}s → refreshing early")
            return await self.refresh_access_token(token_type)

        return token_data.access_token

    def has_streamer_token(self) -> bool:
        """Check if streamer token is configured."""
        return bool(
            "STREAMER_TOKEN" in self.tokens
            and self.tokens["STREAMER_TOKEN"].access_token
            and self.tokens["STREAMER_TOKEN"].refresh_token
        )

    async def get_streamer_token(self) -> str | None:
        """Get streamer token if available."""
        if self.has_streamer_token():
            return await self.get_access_token("STREAMER_TOKEN")
        return None

    def set_streamer_token(
        self,
        access_token: str,
        refresh_token: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        scope: str = "channel:read:redemptions",
    ) -> None:
        """
        Set streamer token data.

        Args:
            access_token: Streamer access token
            refresh_token: Streamer refresh token
            client_id: Client ID (uses bot's if not provided)
            client_secret: Client secret (uses bot's if not provided)
            scope: Token scope
        """
        bot_data = self.tokens.get("BOT_TOKEN")
        if not bot_data:
            raise RuntimeError("Bot token must be configured before streamer token")

        self.tokens["STREAMER_TOKEN"] = TokenData(
            access_token=access_token,
            refresh_token=refresh_token,
            client_id=client_id or bot_data.client_id,
            client_secret=client_secret or bot_data.client_secret,
            scope=scope,
        )

        self._save_config()
        self.logger.info("Streamer token configured successfully")
