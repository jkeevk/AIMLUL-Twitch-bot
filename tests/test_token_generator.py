import configparser
from unittest.mock import MagicMock, patch

import pytest

from src.utils import token_generator as tg


@pytest.fixture
def tmp_config_path(tmp_path):
    """Provide a temporary config file path and patch tg.CONFIG_PATH."""
    tg.CONFIG_PATH = tmp_path / "settings.ini"
    return tg.CONFIG_PATH


def test_save_tokens_creates_new_section(tmp_config_path):
    """Verify save_tokens creates a new config section with correct values."""
    tg.save_tokens("BOT_TOKEN", "acc", "ref", "cid", "csecret")
    config = configparser.ConfigParser()
    config.read(tmp_config_path)
    assert config.get("BOT_TOKEN", "token") == "acc"
    assert config.get("BOT_TOKEN", "refresh_token") == "ref"
    assert config.get("BOT_TOKEN", "client_id") == "cid"
    assert config.get("BOT_TOKEN", "client_secret") == "csecret"


def test_save_tokens_updates_existing(tmp_config_path):
    """Verify save_tokens updates an existing section with new values."""
    config = configparser.ConfigParser()
    config["BOT_TOKEN"] = {"token": "old", "refresh_token": "old", "client_id": "cid", "client_secret": "csecret"}
    with tmp_config_path.open("w") as f:
        config.write(f)

    tg.save_tokens("BOT_TOKEN", "new_acc", "new_ref", "cid2", "csecret2")

    config2 = configparser.ConfigParser()
    config2.read(tmp_config_path)
    assert config2.get("BOT_TOKEN", "token") == "new_acc"
    assert config2.get("BOT_TOKEN", "refresh_token") == "new_ref"
    assert config2.get("BOT_TOKEN", "client_id") == "cid2"
    assert config2.get("BOT_TOKEN", "client_secret") == "csecret2"


def test_create_default_config(tmp_config_path):
    """Verify _create_default_config creates all expected sections."""
    tg._create_default_config()
    config = configparser.ConfigParser()
    config.read(tmp_config_path)
    for section in ["STREAMER_TOKEN", "BOT_TOKEN", "INITIAL_CHANNELS", "COMMANDS", "AUTH"]:
        assert section in config


@patch("src.utils.token_generator.OAuthHTTPServer")
def test_run_oauth_server_returns_code(mock_server_class):
    """Verify run_oauth_server returns the auth code from OAuthHTTPServer."""
    mock_server = MagicMock()
    mock_server.auth_code = "mock_code"
    mock_server.serve_forever = MagicMock()
    mock_server_class.return_value = mock_server

    code = tg.run_oauth_server()

    assert code == "mock_code"
    mock_server.serve_forever.assert_called_once()


@patch("src.utils.token_generator.webbrowser.open")
@patch("src.utils.token_generator.run_oauth_server")
@patch("src.utils.token_generator.requests.post")
def test_get_oauth_token_success(mock_post, mock_run_server, mock_browser, tmp_config_path):
    """Verify get_oauth_token returns token data on successful OAuth flow."""
    config = configparser.ConfigParser()
    config["BOT_TOKEN"] = {"client_id": "cid", "client_secret": "csecret", "scope": "scope1"}
    with tmp_config_path.open("w") as f:
        config.write(f)

    mock_run_server.return_value = "auth_code"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"access_token": "acc", "refresh_token": "ref"}
    mock_post.return_value = mock_response

    token_data = tg.get_oauth_token("BOT_TOKEN")

    assert token_data["access_token"] == "acc"
    assert token_data["refresh_token"] == "ref"
    mock_browser.assert_called_once()
    mock_run_server.assert_called_once()
    mock_post.assert_called_once()


@patch("src.utils.token_generator.webbrowser.open")
@patch("src.utils.token_generator.run_oauth_server")
@patch("src.utils.token_generator.requests.post")
def test_get_oauth_token_failure(mock_post, mock_run_server, mock_browser, tmp_config_path):
    """Verify get_oauth_token returns None on server failure or bad response."""
    config = configparser.ConfigParser()
    config["BOT_TOKEN"] = {"client_id": "cid", "client_secret": "csecret"}
    with tmp_config_path.open("w") as f:
        config.write(f)

    # server returns None
    mock_run_server.return_value = None
    token_data = tg.get_oauth_token("BOT_TOKEN")
    assert token_data is None

    # server returns code but POST fails
    mock_run_server.return_value = "auth_code"
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "bad"
    mock_post.return_value = mock_response

    token_data = tg.get_oauth_token("BOT_TOKEN")
    assert token_data is None
