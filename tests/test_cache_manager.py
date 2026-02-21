import json
from unittest.mock import AsyncMock
import pytest

from src.commands.managers.cache_manager import CacheManager, CHATTERS_KEY, USER_CD_KEY, CMD_CD_KEY
from src.commands.models.chatters import ChatterData


@pytest.fixture
def redis_mock():
    """
    Fixture that provides a mocked Redis client with async methods.
    All Redis interactions in CacheManager will use this mock.
    """
    return AsyncMock()


@pytest.fixture
def cache_manager(redis_mock):
    """
    Fixture that returns a CacheManager instance using the mocked Redis client.
    """
    return CacheManager(redis=redis_mock)


@pytest.mark.asyncio
async def test_user_cooldown(cache_manager, redis_mock):
    """
    Test updating and checking user cooldowns.

    Verifies:
    - `update_user_cooldown` sets the correct key and value in Redis.
    - `can_user_participate` returns True when no cooldown exists.
    - `can_user_participate` returns False when the user is on cooldown.
    """
    # Set cooldown
    await cache_manager.update_user_cooldown("user1", cooldown=10)
    redis_mock.setex.assert_awaited_with(USER_CD_KEY.format("user1"), 10, "1")

    # Simulate no cooldown
    redis_mock.exists.return_value = 0
    assert await cache_manager.can_user_participate("user1") is True

    # Simulate cooldown active
    redis_mock.exists.return_value = 1
    assert await cache_manager.can_user_participate("user1") is False


@pytest.mark.asyncio
async def test_command_cooldown(cache_manager, redis_mock):
    """
    Test setting and checking command cooldowns.

    Verifies:
    - `set_command_cooldown` sets correct Redis key for a command.
    - `is_command_available` correctly reports availability based on Redis.
    """
    await cache_manager.set_command_cooldown("Hello", 20)
    redis_mock.setex.assert_awaited_with(CMD_CD_KEY.format("hello"), 20, "1")

    # Command available
    redis_mock.exists.return_value = 0
    assert await cache_manager.is_command_available("Hello") is True

    # Command on cooldown
    redis_mock.exists.return_value = 1
    assert await cache_manager.is_command_available("Hello") is False


@pytest.mark.asyncio
async def test_chatters_cache(cache_manager, redis_mock):
    """
    Test updating and retrieving chatters cache.

    Verifies:
    - `update_chatters_cache` writes chatters correctly to Redis.
    - `get_cached_chatters` returns empty list when cache is empty.
    - `get_cached_chatters` returns list of ChatterData when cache exists.
    """
    chatters = [ChatterData(id="1", name="user1", display_name="User1")]

    # Update cache
    await cache_manager.update_chatters_cache("channel1", chatters, ttl=123)
    redis_mock.setex.assert_awaited_with(
        CHATTERS_KEY.format("channel1"), 123, json.dumps([c.__dict__ for c in chatters])
    )

    # Cache empty
    redis_mock.get.return_value = None
    assert await cache_manager.get_cached_chatters("channel1") == []

    # Cache exists
    redis_mock.get.return_value = json.dumps([c.__dict__ for c in chatters])
    cached = await cache_manager.get_cached_chatters("channel1")
    assert cached[0].id == "1"


@pytest.mark.asyncio
async def test_active_chatters(cache_manager, redis_mock):
    """
    Test marking users active and retrieving active chatters.

    Verifies:
    - `mark_user_active` updates the sorted set in Redis.
    - `get_active_chatters` correctly decodes bytes and returns a list of dicts.
    """
    username = "user1"
    user_id = "123"

    # Mark user active
    await cache_manager.mark_user_active("channel1", username, user_id)
    redis_mock.zremrangebyscore.assert_awaited()
    redis_mock.zadd.assert_awaited()

    # Mock active users retrieval
    redis_mock.zrangebyscore.return_value = [f"{username}:{user_id}".encode()]
    users = await cache_manager.get_active_chatters("channel1")
    assert users[0]["name"] == username
    assert users[0]["id"] == user_id


@pytest.mark.asyncio
async def test_get_user_id_from_cache(cache_manager, redis_mock):
    """
    Test retrieving a user ID from cached chatters.

    Verifies:
    - `get_user_id` returns correct ID when present in cache.
    - TwitchAPI is not called if cache exists.
    """
    chatters = [ChatterData(id="1", name="user1", display_name="User1")]
    redis_mock.get.return_value = json.dumps([c.__dict__ for c in chatters])

    api_mock = AsyncMock()
    user_id = await cache_manager.get_user_id("user1", "channel1", api_mock)
    assert user_id == "1"
    api_mock.get_chatters.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_user_id_from_api(cache_manager, redis_mock):
    """
    Test retrieving a user ID via TwitchAPI when cache is empty.

    Verifies:
    - Cache miss triggers API call.
    - User ID is correctly retrieved from API response.
    """
    redis_mock.get.return_value = None
    api_mock = AsyncMock()
    api_mock.get_chatters.return_value = [{"user_id": "2", "user_name": "user2"}]

    user_id = await cache_manager.get_user_id("user2", "channel1", api_mock)
    assert user_id == "2"
    api_mock.get_chatters.assert_awaited()


@pytest.mark.asyncio
async def test_force_refresh_chatters(cache_manager, redis_mock):
    """
    Test force refresh of chatters via API.

    Verifies:
    - `_fetch_and_cache_chatters` is called.
    - Returns normalized list of ChatterData.
    """
    api_mock = AsyncMock()
    api_mock.get_chatters.return_value = [{"user_id": "3", "user_name": "user3"}]

    chatters = await cache_manager.force_refresh_chatters("channel1", api_mock)
    assert any(c.id == "3" for c in chatters)


@pytest.mark.asyncio
async def test_normalize_chatter_dict_and_obj(cache_manager):
    """
    Test normalization of raw Twitch user data to ChatterData.

    Verifies:
    - Dict input is converted correctly.
    - Object input with id, name, display_name is converted correctly.
    """
    # Dict input
    c_dict = {"user_id": "4", "user_name": "dictuser"}
    chatter = cache_manager._normalize_chatter(c_dict)
    assert chatter.id == "4"

    # Object input
    class Obj: pass
    obj = Obj()
    obj.id = "5"
    obj.name = "objuser"
    obj.display_name = "ObjUser"
    chatter = cache_manager._normalize_chatter(obj)
    assert chatter.id == "5"


@pytest.mark.asyncio
async def test_find_user_id(cache_manager):
    """
    Test _find_user_id helper.

    Verifies:
    - Returns correct user ID for a known username.
    - Returns None for unknown username.
    """
    chatters = [ChatterData(id="1", name="user1", display_name="User1")]
    assert cache_manager._find_user_id(chatters, "user1") == "1"
    assert cache_manager._find_user_id(chatters, "nonexistent") is None
