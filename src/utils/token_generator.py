import configparser
import logging
import pathlib
import sys
import threading
import urllib.parse as urlparse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, cast

import requests

logger = logging.getLogger(__name__)

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "settings.ini"


class OAuthHTTPServer(HTTPServer):
    """HTTP server storing OAuth auth_code."""

    auth_code: str | None = None


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Twitch OAuth callback."""

    def do_GET(self) -> None:
        """Process GET request from OAuth callback and extract code or error."""
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        query = urlparse.urlparse(self.path).query
        params = urlparse.parse_qs(query)

        server = cast(OAuthHTTPServer, self.server)

        if "code" in params:
            code = params["code"][0]
            server.auth_code = code
            self.wfile.write(
                b"""
                <html>
                <head><title>Twitch Auth Success</title></head>
                <body style="background-color: #9146FF; color: white; text-align: center; padding: 50px;">
                    <h1>Success!</h1>
                    <p>Authorization code received. You can close this window.</p>
                    <p>The token will be saved automatically.</p>
                </body>
                </html>
                """
            )
            logger.info("Authorization code received from Twitch OAuth callback")
        elif "error" in params:
            error = params["error"][0]
            self.wfile.write(f"<h1>Error:</h1><p>{error}</p>".encode())
            logger.error(f"OAuth callback error: {error}")

        threading.Thread(target=server.shutdown, daemon=True).start()

    def log_message(self, msg_format: str, *args: Any) -> None:
        """Suppress default HTTP server log messages."""
        pass


def run_oauth_server(handler_class: type[BaseHTTPRequestHandler]) -> str | None:
    """
    Run HTTP server for OAuth callback and return authorization code.

    Args:
        handler_class: Request handler class for processing callback.

    Returns:
        Authorization code if received, None otherwise.
    """
    server = OAuthHTTPServer(("localhost", 3000), CallbackHandler)
    logger.info("Starting local HTTP server on http://localhost:3000 for OAuth callback")
    server.serve_forever()
    return server.auth_code


def save_tokens(access_token: str, refresh_token: str, client_id: str, client_secret: str) -> None:
    """
    Save OAuth tokens and client credentials to the configuration file.

    Args:
        access_token: OAuth access token
        refresh_token: OAuth refresh token
        client_id: Twitch application client ID
        client_secret: Twitch application client secret
    """
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    if not config.has_section("STREAMER_TOKEN"):
        config.add_section("STREAMER_TOKEN")

    config.set("STREAMER_TOKEN", "token", access_token)
    config.set("STREAMER_TOKEN", "refresh_token", refresh_token)
    config.set("STREAMER_TOKEN", "client_id", client_id)
    config.set("STREAMER_TOKEN", "client_secret", client_secret)

    with pathlib.Path(CONFIG_PATH).open("w") as configfile:
        config.write(configfile)

    logger.info(f"Streamer tokens saved to {CONFIG_PATH}")


def get_oauth_token() -> dict[str, Any] | None:
    """
    Perform OAuth token acquisition flow for Twitch streamer token.

    Opens browser for authorization and runs temporary HTTP server
    to capture the OAuth callback.

    Returns:
        Token data dictionary if successful, None otherwise.
    """
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    if not config.has_option("STREAMER_TOKEN", "client_id") or not config.has_option("STREAMER_TOKEN", "client_secret"):
        logger.error("client_id and client_secret must be specified in settings.ini")
        return None

    client_id = config.get("STREAMER_TOKEN", "client_id")
    client_secret = config.get("STREAMER_TOKEN", "client_secret")
    scope = config.get("STREAMER_TOKEN", "scope", fallback="")
    redirect_uri = "http://localhost:3000"

    auth_url = (
        "https://id.twitch.tv/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        f"&scope={scope}"
        "&force_verify=true"
    )

    logger.info("Opening browser for Twitch OAuth authorization...")
    webbrowser.open(auth_url)

    logger.info("Waiting for OAuth callback on http://localhost:3000...")
    auth_code = run_oauth_server(CallbackHandler)

    if not auth_code:
        logger.error("Failed to receive authorization code")
        return None

    logger.info("Authorization code received successfully, exchanging for token...")

    token_url = "https://id.twitch.tv/oauth2/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }

    response = requests.post(token_url, data=data)
    if response.status_code == 200:
        token_data: dict[str, Any] = response.json()
        logger.info("OAuth token acquired successfully")
        save_tokens(
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            client_id=client_id,
            client_secret=client_secret,
        )
        return token_data
    else:
        logger.error(f"Error acquiring token: {response.status_code} {response.text}")
        return None


def _create_default_config() -> None:
    """Create the default configuration file with required sections."""
    config = configparser.ConfigParser()
    config["STREAMER_TOKEN"] = {
        "token": "",
        "client_id": "",
        "client_secret": "",
        "refresh_token": "",
    }
    config["INITIAL_CHANNELS"] = {"channels": ""}
    config["SETTINGS"] = {
        "command_delay_time": "45",
        "refresh_token_delay_time": "7200",
    }

    with pathlib.Path(CONFIG_PATH).open("w") as configfile:
        config.write(configfile)

    logger.info(f"Default configuration created: {CONFIG_PATH}")


def main() -> None:
    """Main entry point for the token generator script."""
    logger.info("Twitch Token Generator started")

    if not pathlib.Path(CONFIG_PATH).exists():
        logger.warning(f"Configuration file not found: {CONFIG_PATH}")
        _create_default_config()
        logger.info("Please add client_id and client_secret from Twitch Developer Console and rerun the script")
        sys.exit(0)

    token_data = get_oauth_token()
    if token_data:
        logger.info("Setup complete! You can now run the bot with new tokens")
    else:
        logger.error("Failed to acquire token. Check settings and try again")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    main()
