import time
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from twitchio.ext.commands import Context

from tests.conftest import DummyAuthor, DummyChannel, DummyCtx

VOTEBAN_REQUIRED_VOTES = 10
VOTEBAN_TIMEOUT_SECONDS = 600
VOTEBAN_WINDOW_SECONDS = 300


@pytest.mark.asyncio
async def test_handle_club_no_privilege(simple_commands_game, ctx_normal):
    """Test that a normal user without privileges cannot execute the club command."""
    await simple_commands_game.handle_club_command(cast(Context, ctx_normal))
    assert ctx_normal.sent == []


@pytest.mark.asyncio
async def test_handle_club_success(
    simple_commands_game, ctx_privileged, mock_cache_manager, mock_api, mock_user_manager
):
    """Test that a privileged user successfully executes the club command."""

    class RealChatter:
        """Simulated chatter returned by the cache manager."""

        def __init__(self, name):
            self.name = name

    dummy_chatter = RealChatter("SomeChatter")
    mock_cache_manager.get_cached_chatters.return_value = [dummy_chatter]

    mock_user_manager.get_user_id.return_value = "target-id"
    mock_api.timeout_user.return_value = (200, {})

    with patch("src.commands.games.simple_commands.random.choice") as mock_choice:
        mock_choice.return_value = dummy_chatter
        await simple_commands_game.handle_club_command(cast(Context, ctx_privileged))

    assert any("бьёт дрыном" in msg for msg in ctx_privileged.sent)


@pytest.mark.asyncio
async def test_handle_butt_low_chance(simple_commands_game, ctx_normal):
    """
    Test the 'butt' command with a low random chance (< 90).

    Expected output is a percentage message.
    """
    with patch("src.commands.games.simple_commands.random.randint") as mock_randint:
        mock_randint.return_value = 50
        await simple_commands_game.handle_butt_command(cast(Context, ctx_normal))

    assert len(ctx_normal.sent) == 1
    assert "воняет на 50%" in ctx_normal.sent[0]


@pytest.mark.asyncio
async def test_handle_butt_high_chance_100(simple_commands_game, ctx_normal, mock_api, mock_user_manager):
    """
    Test the 'butt' command with maximum chance (100).

    Expected output is a message indicating washing.
    """
    mock_user_manager.get_user_id.return_value = "normal-id"
    mock_api.timeout_user.return_value = (200, {})

    with patch("src.commands.games.simple_commands.random.randint") as mock_randint:
        mock_randint.return_value = 100
        await simple_commands_game.handle_butt_command(cast(Context, ctx_normal))

    assert any("washing" in msg for msg in ctx_normal.sent)


@pytest.mark.asyncio
async def test_handle_butt_high_chance_privileged(simple_commands_game, ctx_privileged, mock_api, mock_user_manager):
    """
    Test the 'butt' command with high chance for a privileged user.

    The command should skip sending a timeout and instead send a joke message.
    """
    mock_user_manager.get_user_id.return_value = "privileged-id"
    mock_api.timeout_user.return_value = (200, {})

    with patch("src.commands.games.simple_commands.random.randint") as mock_randint:
        mock_randint.return_value = 95
        await simple_commands_game.handle_butt_command(cast(Context, ctx_privileged))

    assert any("Шучу, не отправлен" in msg for msg in ctx_privileged.sent)


@pytest.mark.asyncio
async def test_handle_test_barrel_not_admin(simple_commands_game, ctx_normal):
    """Test that a normal user cannot execute the test barrel command."""
    await simple_commands_game.handle_test_barrel_command(cast(Context, ctx_normal))
    assert ctx_normal.sent == []


@pytest.mark.asyncio
async def test_handle_test_barrel_success(
    simple_commands_game, privileged_author, channel, mock_cache_manager, mock_user_manager, mock_api
):
    """
    Test that an admin successfully executes the test barrel command.

    Selecting a subset of chatters.
    """
    simple_commands_game.bot.config["admins"] = [privileged_author.name.lower()]

    class RealChatter:
        """Simulated chatter for testing purposes."""

        def __init__(self, name):
            self.name = name

    dummy_chatters = [RealChatter(f"User{i}") for i in range(5)]
    mock_cache_manager.filter_chatters.return_value = dummy_chatters
    mock_user_manager.get_user_id.return_value = "test-id"
    mock_api.timeout_user.return_value = (200, {})

    with patch("src.commands.games.simple_commands.random.sample") as mock_sample:
        mock_sample.return_value = dummy_chatters[:3]

        ctx = DummyCtx(privileged_author, channel)
        await simple_commands_game.handle_test_barrel_command(cast(Context, ctx))

    assert any("Тест." in msg for msg in ctx.sent)


@pytest.mark.asyncio
async def test_handle_club_cooldown(simple_commands_game, ctx_privileged, mock_cache_manager):
    """Test that the club command respects cooldowns and does not execute if on cooldown."""

    class RealChatter:
        """Simulated chatter for testing purposes."""

        def __init__(self, name):
            self.name = name

    dummy_chatter = RealChatter("SomeChatter")
    mock_cache_manager.get_cached_chatters.return_value = [dummy_chatter]

    simple_commands_game.command_handler.get_current_time.return_value = 1000
    mock_cache_manager.command_cooldowns["club"] = 1000

    await simple_commands_game.handle_club_command(cast(Context, ctx_privileged))
    assert len(ctx_privileged.sent) == 0


@pytest.mark.asyncio
async def test_handle_voteban_not_enough_votes(simple_commands_game, ctx_normal):
    """Test that voteban does nothing if votes are below the threshold."""
    ctx_normal.message.content = "!voteban @target"
    simple_commands_game.command_handler.voteban_state = {
        "target": None,
        "votes": set(),
        "start_time": 0,
    }

    # The first vote should not trigger a timeout
    await simple_commands_game.handle_voteban_command(cast(Context, ctx_normal))
    assert ctx_normal.sent == []


@pytest.mark.asyncio
async def test_handle_voteban_timeout_success(simple_commands_game):
    """Test voteban command triggers timeout after reaching the vote threshold."""
    # Create author and channel
    normal_author = DummyAuthor(10, "voter10")
    channel = DummyChannel("test_channel")

    # Create command context with the voteban message
    ctx = DummyCtx(author=normal_author, channel=channel, message_content="!voteban @target")

    # Simulate existing 9 votes for the target
    simple_commands_game.command_handler.voteban_state = {
        "target": "target",
        "votes": {f"voter{i}" for i in range(1, 10)},  # 9 votes
        "start_time": time.time(),
    }

    # Patch user_manager and api
    with (
        patch.object(simple_commands_game.command_handler, "user_manager", create=True) as um_mock,
        patch.object(simple_commands_game, "api", create=True) as api_mock,
    ):

        um_mock.get_user_id = AsyncMock(return_value="target-id")
        api_mock.timeout_user = AsyncMock(return_value=(200, {}))

        # Call the voteban command, the 10th vote should trigger timeout
        await simple_commands_game.handle_voteban_command(cast(Context, ctx))

    # Assert that a timeout message was sent
    assert any("изгнан" in msg for msg in ctx.sent)


@pytest.mark.asyncio
async def test_handle_voteban_self_vote(simple_commands_game, ctx_normal):
    """Test that voteban ignores self-votes."""
    ctx_normal.author.name = "target"
    ctx_normal.message.content = "!voteban @target"
    simple_commands_game.command_handler.voteban_state = {
        "target": None,
        "votes": set(),
        "start_time": 0,
    }

    await simple_commands_game.handle_voteban_command(cast(Context, ctx_normal))
    assert ctx_normal.sent == []


@pytest.mark.asyncio
async def test_handle_voteban_no_target(simple_commands_game, ctx_normal):
    """Test that voteban does nothing if no target is provided."""
    ctx_normal.message.content = "!voteban"
    simple_commands_game.command_handler.voteban_state = {
        "target": None,
        "votes": set(),
        "start_time": 0,
    }

    await simple_commands_game.handle_voteban_command(cast(Context, ctx_normal))
    assert ctx_normal.sent == []
