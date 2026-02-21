import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.twitch_api import TwitchAPI


@pytest.mark.asyncio
async def test_bot_token_and_headers():
    """Test that bot_token and get_headers return correct values."""
    mock_bot = MagicMock()
    # Provide fake token and client_id
    mock_bot.token_manager.tokens = {
        "BOT_TOKEN": MagicMock(access_token="12345TOKEN", client_id="CLIENTID")
    }
    api = TwitchAPI(mock_bot)

    # Check token retrieval
    token = api.bot_token()
    assert token == "12345TOKEN"

    # Check headers construction
    headers = api.get_headers()
    assert headers["Authorization"] == "Bearer 12345TOKEN"
    assert headers["Client-Id"] == "CLIENTID"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_ensure_session_creates_session():
    """Test that _ensure_session creates an aiohttp session if none exists."""
    mock_bot = MagicMock()
    mock_bot.token_manager.tokens = {"BOT_TOKEN": MagicMock(access_token="t", client_id="c")}
    api = TwitchAPI(mock_bot)

    # Initially no session exists
    assert api.session is None
    await api._ensure_session()
    # Session should now exist and be open
    assert api.session is not None
    assert not api.session.closed


@pytest.mark.asyncio
async def test_request_with_token_refresh_refreshes_on_401():
    """Test that _request_with_token_refresh refreshes token on 401 response."""
    mock_bot = MagicMock()
    mock_token_manager = AsyncMock()
    mock_bot.token_manager = mock_token_manager
    mock_bot.user_id = "mod123"
    mock_bot.token_manager.tokens = {"BOT_TOKEN": MagicMock(access_token="t", client_id="c")}

    api = TwitchAPI(mock_bot)
    await api._ensure_session()

    # Mock a response that returns 401 first
    response_mock = AsyncMock()
    response_mock.__aenter__.return_value.status = 401
    response_mock.__aenter__.return_value.json = AsyncMock(return_value={})

    # Patch session request and refresh_headers
    with patch.object(api.session, "request", return_value=response_mock), \
            patch.object(api, "refresh_headers", AsyncMock()):
        status, data = await api._request_with_token_refresh("get", "http://test")

    # Token refresh should have been called
    mock_token_manager.refresh_access_token.assert_awaited_with("BOT_TOKEN")
    assert status == 401


@pytest.mark.asyncio
async def test_get_broadcaster_id_from_cache():
    """Test that get_broadcaster_id returns cached value if available."""
    mock_bot = MagicMock()
    mock_bot.cache_manager.redis.get = AsyncMock(return_value="cached123")
    api = TwitchAPI(mock_bot)

    broadcaster_id = await api.get_broadcaster_id("channel")
    assert broadcaster_id == "cached123"


@pytest.mark.asyncio
async def test_get_broadcaster_id_fetch_and_cache():
    """Test fetching broadcaster ID from API and storing it in cache."""
    mock_bot = MagicMock()
    mock_bot.cache_manager.redis.get = AsyncMock(return_value=None)
    mock_bot.cache_manager.redis.setex = AsyncMock()

    api = TwitchAPI(mock_bot)
    api._get_user_id = AsyncMock(return_value="new123")

    broadcaster_id = await api.get_broadcaster_id("channel")
    assert broadcaster_id == "new123"
    # Ensure the value was cached
    mock_bot.cache_manager.redis.setex.assert_awaited_once()


@pytest.mark.asyncio
async def test_timeout_user_calls_api():
    """Test that timeout_user calls the API and returns expected response."""
    mock_bot = MagicMock()
    mock_bot.user_id = "mod123"
    api = TwitchAPI(mock_bot)
    api.get_broadcaster_id = AsyncMock(return_value="broad123")
    api._request_with_token_refresh = AsyncMock(return_value=(200, {"ok": True}))

    status, data = await api.timeout_user("user1", "channel", 60, "reason")
    assert status == 200
    assert data == {"ok": True}


@pytest.mark.asyncio
async def test_get_user_id_returns_id():
    """Test that _get_user_id returns user ID from API response."""
    mock_bot = MagicMock()
    mock_bot.token_manager.tokens = {"BOT_TOKEN": MagicMock(access_token="t", client_id="c")}
    mock_bot.user_id = "mod123"
    api = TwitchAPI(mock_bot)
    api._request_with_token_refresh = AsyncMock(return_value=(200, {"data": [{"id": "uid123"}]}))

    user_id = await api._get_user_id("user1")
    assert user_id == "uid123"


@pytest.mark.asyncio
async def test_close_session_closes_if_open():
    """Test that close() properly closes an active aiohttp session."""
    mock_bot = MagicMock()
    api = TwitchAPI(mock_bot)
    await api._ensure_session()

    await api.close()
    assert api.session.closed


@pytest.mark.asyncio
async def test_close_session_when_none_or_closed():
    """Test that close() works when session is None or already closed."""
    mock_bot = MagicMock()
    api = TwitchAPI(mock_bot)

    # Session was never created
    await api.close()  # should not raise

    # Session already closed
    await api._ensure_session()
    await api.session.close()
    await api.close()  # should not raise
