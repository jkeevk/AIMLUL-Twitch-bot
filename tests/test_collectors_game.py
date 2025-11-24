import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import DummyAuthor, DummyMessage


@pytest.mark.asyncio
async def test_handle_applecat_privileged_user(collectors_game):
    """Ensure privileged users do not get timed out when using applecat command."""
    author = DummyAuthor("user2", "PrivilegedUser2", privileged=True)
    author.is_mod = True
    message = DummyMessage(author)

    await collectors_game.handle_applecat(message)

    collectors_game.api.timeout_user.assert_not_called()


@pytest.mark.asyncio
async def test_handle_gnome_user_on_cooldown(collectors_game):
    """Test that a user on cooldown does not trigger timeout."""
    author = DummyAuthor("user3", "NormalUser")
    message = DummyMessage(author)
    collectors_game.cache_manager.can_user_participate.return_value = False

    await collectors_game.handle_gnome(message)

    collectors_game.api.timeout_user.assert_not_called()


@pytest.mark.asyncio
async def test_handle_gnome_successful_participation(collectors_game):
    """Verify successful participation of a user in the gnome collector."""
    author = DummyAuthor("user123", "TestUser")
    message = DummyMessage(author)

    gnome = collectors_game.collectors["gnome"]
    assert gnome.participants == []

    await collectors_game.handle_gnome(message)

    assert contains_user(gnome.participants, author.id, author.name)
    collectors_game.cache_manager.update_user_cooldown.assert_called_once_with(author.id)


@pytest.mark.asyncio
async def test_handle_gnome_collector_full_and_timeout(collectors_game):
    """
    Test that the gnome collector triggers timeout when full.

    and resets participants.
    """
    collectors_game.api.timeout_user = AsyncMock(return_value=(200, {}))
    collectors_game.cache_manager.can_user_participate.return_value = True

    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()

    gnome = collectors_game.collectors["gnome"]

    # Fill collector to required participants
    for i in range(gnome.config.required_participants):
        gnome.add(f"user{i}", f"User{i}")

    # Add new participant to trigger timeout
    author = DummyAuthor("userX", "UserX")
    message = DummyMessage(author)
    message.channel = mock_channel

    await collectors_game.handle_gnome(message)

    collectors_game.api.timeout_user.assert_called_once()
    mock_channel.send.assert_called_once()
    assert len(gnome.participants) == 0


@pytest.mark.asyncio
async def test_handle_applecat_collector_full_and_timeout(collectors_game):
    """Test that applecat collector triggers timeout and resets participants when full."""
    author = DummyAuthor("user5", "User5")
    message = DummyMessage(author)
    collectors_game.cache_manager.can_user_participate.return_value = True

    applecat = collectors_game.collectors["applecatpanik"]

    for i in range(applecat.config.required_participants):
        applecat.add(f"user{i}", f"User{i}")

    await collectors_game.handle_applecat(message)

    collectors_game.api.timeout_user.assert_called_once()
    args = collectors_game.api.timeout_user.call_args[1]
    assert args["duration"] == applecat.config.duration
    assert args["reason"] == applecat.config.reason


@pytest.mark.asyncio
async def test_handle_gnome_api_error(collectors_game):
    """Ensure collector resets even if the API returns an error."""
    author = DummyAuthor("user6", "User6")
    message = DummyMessage(author)
    collectors_game.cache_manager.can_user_participate.return_value = True

    collectors_game.api.timeout_user = AsyncMock(return_value=(401, "Unauthorized"))

    gnome = collectors_game.collectors["gnome"]
    for i in range(gnome.config.required_participants):
        gnome.add(f"user{i}", f"User{i}")

    await collectors_game.handle_gnome(message)

    assert len(gnome.participants) == 0


@pytest.mark.asyncio
async def test_collector_auto_reset(collectors_game):
    """Test automatic reset of collector after inactivity."""
    author = DummyAuthor("user7", "User7")
    message = DummyMessage(author)
    collectors_game.cache_manager.can_user_participate.return_value = True
    collectors_game.api.timeout_user = AsyncMock(return_value=(200, {}))

    gnome = collectors_game.collectors["gnome"]
    gnome.add("old_user", "OldUser")
    gnome.last_added = time.time() - (gnome.config.reset_time + 10)

    await collectors_game.handle_gnome(message)

    assert len(gnome.participants) == 1
    assert contains_user(gnome.participants, author.id)


@pytest.mark.asyncio
async def test_handle_command_not_implemented(collectors_game):
    """Ensure that unimplemented commands do not raise exceptions."""
    ctx = MagicMock()
    await collectors_game.handle_command(ctx)


@pytest.mark.asyncio
async def test_collector_configurations(collectors_game):
    """Verify that collector configurations are set correctly."""
    gnome = collectors_game.collectors["gnome"]
    applecat = collectors_game.collectors["applecatpanik"]

    assert gnome.config.name == "gnome"
    assert gnome.config.reset_time == 300
    assert gnome.config.reason == "гном"
    assert gnome.config.duration == 60
    assert gnome.config.required_participants == 3

    assert applecat.config.name == "applecatpanik"
    assert applecat.config.reset_time == 300
    assert applecat.config.reason == "не бегать"
    assert applecat.config.duration == 60
    assert applecat.config.required_participants == 3


@pytest.mark.asyncio
async def test_handle_gnome_exception_handling(collectors_game):
    """Ensure that exceptions in gnome command handling do not break execution."""
    author = DummyAuthor("user8", "User8")
    message = DummyMessage(author)
    collectors_game.cache_manager.can_user_participate.side_effect = Exception("Test error")

    await collectors_game.handle_gnome(message)


@pytest.mark.asyncio
async def test_handle_applecat_exception_handling(collectors_game):
    """Ensure that exceptions in applecat command handling do not break execution."""
    author = DummyAuthor("user9", "User9")
    message = DummyMessage(author)
    collectors_game.cache_manager.can_user_participate.side_effect = Exception("Test error")

    await collectors_game.handle_applecat(message)


def contains_user(participants, user_id, user_name=None):
    """
    Check if a user is in the participants list.

    Args:
        participants (list[tuple]): List of tuples (user_id, user_name)
        user_id (str): User ID to check
        user_name (str, optional): User name to check

    Returns:
        bool: True if user exists in participants, False otherwise
    """
    return any(uid == user_id and (user_name is None or uname == user_name) for uid, uname in participants)
