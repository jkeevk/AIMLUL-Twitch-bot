import configparser
import os
import sys
import threading
import urllib.parse as urlparse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, Dict, Any

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, "settings.ini")


class CallbackHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for OAuth callback processing.

    Handles the redirect from Twitch OAuth authorization and extracts
    the authorization code or error from the callback URL.
    """

    def do_GET(self) -> None:
        """
        Process GET request from OAuth callback.

        Extracts authorization code from URL parameters and triggers
        server shutdown after processing the callback.
        """
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        query = urlparse.urlparse(self.path).query
        params = urlparse.parse_qs(query)

        if "code" in params:
            code = params["code"][0]
            self.server.auth_code = code
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
        elif "error" in params:
            error = params["error"][0]
            self.wfile.write(f"<h1>Error:</h1><p>{error}</p>".encode())

        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP server log messages."""
        pass


def save_tokens(access_token: str, refresh_token: str, client_id: str, client_secret: str) -> None:
    """
    Save OAuth tokens and client credentials to configuration file.

    Args:
        access_token: OAuth access token
        refresh_token: OAuth refresh token
        client_id: Twitch application client ID
        client_secret: Twitch application client secret
    """
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    if not config.has_section("TOKEN"):
        config.add_section("TOKEN")

    config.set("TOKEN", "token", access_token)
    config.set("TOKEN", "refresh_token", refresh_token)
    config.set("TOKEN", "client_id", client_id)
    config.set("TOKEN", "client_secret", client_secret)

    with open(CONFIG_PATH, "w") as configfile:
        config.write(configfile)

    print(f"Tokens saved to {CONFIG_PATH}")


def get_oauth_token() -> Optional[Dict[str, Any]]:
    """
    Perform OAuth token acquisition flow.

    Returns:
        Token data dictionary if successful, None otherwise
    """
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    if not config.has_option("TOKEN", "client_id") or not config.has_option(
            "TOKEN", "client_secret"
    ):
        print("Error: client_id and client_secret must be specified in settings.ini")
        return None

    client_id = config.get("TOKEN", "client_id")
    client_secret = config.get("TOKEN", "client_secret")
    scope = config.get("TOKEN", "scope")
    redirect_uri = "http://localhost:3000"

    server = HTTPServer(("localhost", 3000), CallbackHandler)
    server.auth_code = None

    auth_url = (
        "https://id.twitch.tv/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        "&response_type=code"
        f"&scope={scope}"
        "&force_verify=true"
    )

    print("Opening browser for authorization...")
    webbrowser.open(auth_url)

    print("Waiting for callback on http://localhost:3000...")
    print("After Twitch authorization, token will be saved automatically")
    server.serve_forever()

    if not server.auth_code:
        print("Failed to receive authorization code")
        return None

    print("Authorization code received successfully")

    token_url = "https://id.twitch.tv/oauth2/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": server.auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }

    print("Exchanging authorization code for token...")
    response = requests.post(token_url, data=data)

    if response.status_code == 200:
        token_data = response.json()
        print("Token acquired successfully")

        save_tokens(
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            client_id=client_id,
            client_secret=client_secret,
        )

        return token_data
    else:
        print(f"Error acquiring token: {response.status_code}")
        print(response.text)
        return None


def _create_default_config() -> None:
    """Create default configuration file with required sections."""
    config = configparser.ConfigParser()
    config["TOKEN"] = {
        "token": "",
        "client_id": "",
        "client_secret": "",
        "refresh_token": "",
    }
    config["INITIAL_CHANNELS"] = {"channels": ""}
    config["SETTINGS"] = {
        "command_delay_time": "45",
        "refresh_token_delay_time": "7200"
    }

    with open(CONFIG_PATH, "w") as configfile:
        config.write(configfile)

    print(f"Default configuration created: {CONFIG_PATH}")


def main() -> None:
    """Main entry point for token generator script."""
    print("\n" + "=" * 50)
    print(" Twitch Token Generator".center(50))
    print("=" * 50 + "\n")

    if not os.path.exists(CONFIG_PATH):
        print(f"Configuration file not found: {CONFIG_PATH}")
        print("Creating default configuration file...")

        _create_default_config()
        print("Please add client_id and client_secret from Twitch Developer Console")
        print("Then run the script again")
        sys.exit(0)

    token_data = get_oauth_token()

    if token_data:
        print("\nSetup complete! You can now run the bot with new tokens")
    else:
        print("\nFailed to acquire token. Check settings and try again")


if __name__ == "__main__":
    main()
