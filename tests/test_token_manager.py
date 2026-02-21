import configparser
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from src.utils.token_manager import TokenManager, TokenData

@pytest.fixture
def tmp_config(tmp_path):
    """
    Create a temporary INI config file with BOT_TOKEN section.
    """
    config_file = tmp_path / "config.ini"
    config = configparser.ConfigParser()
    config.add_section("BOT_TOKEN")
    config.set("BOT_TOKEN", "token", "old_access")
    config.set("BOT_TOKEN", "refresh_token", "old_refresh")
    config.set("BOT_TOKEN", "client_id", "cid")
    config.set("BOT_TOKEN", "client_secret", "csecret")
    with config_file.open("w") as f:
        config.write(f)
    return config_file

def test_load_tokens(tmp_config):
    """
    Verify that TokenManager loads tokens correctly from config.
    """
    manager = TokenManager(str(tmp_config))
    token_data = manager.tokens["BOT_TOKEN"]

    assert token_data.access_token == "old_access"
    assert token_data.refresh_token == "old_refresh"
    assert token_data.client_id == "cid"
    assert token_data.client_secret == "csecret"
    assert token_data.scope == ""

def test_save_config(tmp_config):
    """
    Verify that _save_config writes updated tokens to the INI file.
    """
    manager = TokenManager(str(tmp_config))
    manager.tokens["BOT_TOKEN"].access_token = "new_access"
    manager.tokens["BOT_TOKEN"].refresh_token = "new_refresh"

    manager._save_config()

    config = configparser.ConfigParser()
    config.read(tmp_config)
    assert config.get("BOT_TOKEN", "token") == "new_access"
    assert config.get("BOT_TOKEN", "refresh_token") == "new_refresh"

def test_has_streamer_token(tmp_config):
    """
    Check that has_streamer_token returns True only if streamer token exists.
    """
    manager = TokenManager(str(tmp_config))
    assert not manager.has_streamer_token()

    # Add streamer token manually
    manager.tokens["STREAMER_TOKEN"] = TokenData(
        "a", "r", "cid", "csecret"
    )
    assert manager.has_streamer_token()

def test_set_streamer_token(tmp_config):
    """
    Verify that set_streamer_token correctly stores streamer token and saves config.
    """
    manager = TokenManager(str(tmp_config))

    manager.set_streamer_token(
        access_token="s_access",
        refresh_token="s_refresh",
        client_id=None,
        client_secret=None,
    )

    token = manager.tokens["STREAMER_TOKEN"]
    # Should inherit client_id and client_secret from BOT_TOKEN
    assert token.client_id == "cid"
    assert token.client_secret == "csecret"
    assert token.access_token == "s_access"
    assert token.refresh_token == "s_refresh"

@pytest.mark.asyncio
async def test_validate_token_success():
    manager = TokenManager(config_path="dummy.ini")

    # Mock the response object
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"client_id": "cid"})

    # Async context manager for session.get
    mock_get_ctx = AsyncMock()
    mock_get_ctx.__aenter__.return_value = mock_response
    mock_get_ctx.__aexit__.return_value = None

    # Mock ClientSession instance
    mock_session_instance = MagicMock()
    mock_session_instance.get.return_value = mock_get_ctx

    # Patch ClientSession to return an object with proper __aenter__/__aexit__
    mock_client_session = MagicMock()
    mock_client_session.__aenter__.return_value = mock_session_instance
    mock_client_session.__aexit__.return_value = None

    with patch("aiohttp.ClientSession", return_value=mock_client_session):
        data = await manager.validate_token("token")
        assert data["client_id"] == "cid"

@pytest.mark.asyncio
async def test_validate_token_failure():
    """
    Validate that validate_token returns None on invalid token.
    """
    manager = TokenManager(config_path="dummy.ini")

    fake_response = AsyncMock()
    fake_response.status = 401

    with patch("aiohttp.ClientSession.get", return_value=fake_response):
        data = await manager.validate_token("token")
        assert data is None

@pytest.mark.asyncio
async def test_refresh_access_token(tmp_path):
    # Prepare config file
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        "[BOT_TOKEN]\ntoken=old\nrefresh_token=old\nclient_id=cid\nclient_secret=csecret\n"
    )
    manager = TokenManager(str(config_file))

    new_access = "new_access_token"
    new_refresh = "new_refresh_token"

    # Mock response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"access_token": new_access, "refresh_token": new_refresh})

    # Async context manager for session.post
    mock_post_ctx = AsyncMock()
    mock_post_ctx.__aenter__.return_value = mock_response
    mock_post_ctx.__aexit__.return_value = None

    # Mock ClientSession instance
    mock_session_instance = MagicMock()
    mock_session_instance.post.return_value = mock_post_ctx

    # Patch ClientSession to return an object with proper __aenter__/__aexit__
    mock_client_session = MagicMock()
    mock_client_session.__aenter__.return_value = mock_session_instance
    mock_client_session.__aexit__.return_value = None

    with patch("aiohttp.ClientSession", return_value=mock_client_session), \
         patch.object(manager, "_save_config") as mock_save:
        token = await manager.refresh_access_token("BOT_TOKEN")
        assert token == new_access
        assert manager.tokens["BOT_TOKEN"].refresh_token == new_refresh
        mock_save.assert_called_once()

@pytest.mark.asyncio
async def test_get_access_token_refresh(tmp_config):
    """
    Ensure get_access_token calls refresh if token is invalid.
    """
    manager = TokenManager(str(tmp_config))

    # Patch validate_token to return None → triggers refresh
    with patch.object(manager, "validate_token", return_value=None), \
         patch.object(manager, "refresh_access_token", AsyncMock(return_value="refreshed")):
        token = await manager.get_access_token("BOT_TOKEN")
        assert token == "refreshed"
