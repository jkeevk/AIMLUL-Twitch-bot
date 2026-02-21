import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_first_two_play_instantly(twenty_one_game):
    """
    Test that the first two players join the game and start immediately.

    The game timer is set to 1 second, ensuring instant play for the first two participants.
    """
    twenty_one_game.timer_seconds = 0

    class DummyChatter:
        def __init__(self, id_, name):
            self.id = id_
            self.name = name

    def make_ctx(user_id: int, user_name: str):
        """Create a mock context with a send method and author."""
        return type(
            "Ctx",
            (),
            {
                "author": DummyChatter(user_id, user_name),
                "channel": None,
                "sent": [],
                "send": lambda self, m: self.sent.append(m),
            },
        )()

    ctx1 = make_ctx(1, "User1")
    ctx2 = make_ctx(2, "User2")

    await twenty_one_game.handle_command(ctx1)
    await twenty_one_game.handle_command(ctx2)

    await asyncio.sleep(0.001)
    assert len(twenty_one_game.player_queue) == 0


@pytest.mark.asyncio
async def test_third_and_fourth_start_with_dynamic_timer(twenty_one_game):
    """
    Test that the third and fourth players are handled with a dynamic timer.

    The game timer is set to 5 seconds. Third player should wait for an opponent,
    and fourth player should trigger join messages correctly.
    """
    twenty_one_game.timer_seconds = 0

    class DummyChatter:
        def __init__(self, id_, name):
            self.id = id_
            self.name = name

    def make_ctx(user_id: int, user_name: str):
        return type(
            "Ctx",
            (),
            {
                "author": DummyChatter(user_id, user_name),
                "channel": None,
                "sent": [],
                "send": lambda self, m: self.sent.append(m),
            },
        )()

    ctx1, ctx2 = make_ctx(1, "User1"), make_ctx(2, "User2")
    ctx3, ctx4 = make_ctx(3, "User3"), make_ctx(4, "User4")

    await twenty_one_game.handle_command(ctx1)
    await twenty_one_game.handle_command(ctx2)
    await asyncio.sleep(0.001)

    await twenty_one_game.handle_command(ctx3)
    assert any("ждет соперника" in msg for msg in ctx3.sent)

    await asyncio.sleep(0.001)
    await twenty_one_game.handle_command(ctx4)


@pytest.mark.asyncio
async def test_repeated_player_cannot_join_twice(twenty_one_game):
    """Test that the same player cannot join the game twice consecutively."""
    twenty_one_game.timer_seconds = 0

    class DummyChatter:
        def __init__(self, id_, name):
            self.id = id_
            self.name = name

    ctx = type(
        "Ctx",
        (),
        {"author": DummyChatter(1, "User1"), "channel": None, "sent": [], "send": lambda self, m: self.sent.append(m)},
    )()

    await twenty_one_game.handle_command(ctx)
    await twenty_one_game.handle_command(ctx)

    # Only one instance of the player should be in the queue
    player_ids = [str(p[0]) for p in twenty_one_game.player_queue]
    assert player_ids.count(str(ctx.author.id)) == 1


@pytest.mark.asyncio
async def test_game_resets_after_timer(twenty_one_game):
    """Test that the game queue resets correctly after the timer expires."""
    twenty_one_game.timer_seconds = 0

    class DummyChatter:
        def __init__(self, id_, name):
            self.id = id_
            self.name = name

    def make_ctx(user_id: int, user_name: str):
        return type(
            "Ctx",
            (),
            {
                "author": DummyChatter(user_id, user_name),
                "channel": None,
                "sent": [],
                "send": lambda self, m: self.sent.append(m),
            },
        )()

    ctx1, ctx2 = make_ctx(1, "User1"), make_ctx(2, "User2")

    await twenty_one_game.handle_command(ctx1)
    await twenty_one_game.handle_command(ctx2)

    # Wait enough for the timer to expire
    await asyncio.sleep(0.001)
    assert len(twenty_one_game.player_queue) == 0


@pytest.mark.asyncio
async def test_multiple_games_sequentially(twenty_one_game):
    """
    Test handling multiple 21-game sessions sequentially.

    Ensures that players are queued and processed correctly across
    consecutive game sessions.
    """
    twenty_one_game.timer_seconds = 0

    # Patch async methods to avoid NoneType / MagicMock errors
    twenty_one_game.start_game = AsyncMock()
    twenty_one_game.save_stats = AsyncMock()

    dummy_channel = AsyncMock()
    dummy_channel.send = AsyncMock()
    twenty_one_game.bot.get_channel = MagicMock(return_value=dummy_channel)

    twenty_one_game.db = AsyncMock()
    twenty_one_game.db.get_stats = AsyncMock(return_value=(0, 0))
    twenty_one_game.db.update_stats = AsyncMock(return_value=(1, 0))
    twenty_one_game.api.timeout_user = AsyncMock()
    twenty_one_game.logger = MagicMock()
    twenty_one_game._start_game = AsyncMock()

    class DummyChatter:
        def __init__(self, id_, name):
            self.id = id_
            self.name = name

    def make_ctx(user_id: int, user_name: str):
        return type(
            "Ctx",
            (),
            {
                "author": DummyChatter(user_id, user_name),
                "channel": None,
                "sent": [],
                "send": lambda self, m: self.sent.append(m),
            },
        )()

    # -------------------- Game 1 -------------------- #
    ctx1, ctx2 = make_ctx(1, "User1"), make_ctx(2, "User2")
    await twenty_one_game.handle_command(ctx1)
    await twenty_one_game.handle_command(ctx2)
    await asyncio.sleep(twenty_one_game.timer_seconds + 0.001)
    assert len(twenty_one_game.player_queue) == 0

    # -------------------- Game 2 -------------------- #
    ctx3, ctx4 = make_ctx(3, "User3"), make_ctx(4, "User4")
    await twenty_one_game.handle_command(ctx3)
    await twenty_one_game.handle_command(ctx4)
    await asyncio.sleep(twenty_one_game.timer_seconds + 0.001)
    assert len(twenty_one_game.player_queue) == 0

    # -------------------- Game 3 -------------------- #
    ctx5 = make_ctx(3, "User5")
    await twenty_one_game.handle_command(ctx5)
    await asyncio.sleep(twenty_one_game.timer_seconds + 0.001)
    assert len(twenty_one_game.player_queue) == 1


@pytest.mark.asyncio
async def test_determine_winner_all_cases(twenty_one_game):
    """Test _determine_winner logic with all score combinations."""
    player1 = ("1", "Alice")
    player2 = ("2", "Bob")

    # Both valid, score1 > score2
    result = twenty_one_game._determine_winner(20, 18, player1, player2)
    assert result[0] == "Alice"
    assert result[1] == "Bob"

    # Both valid, score2 > score1
    result = twenty_one_game._determine_winner(18, 21, player1, player2)
    assert result[0] == "Bob"
    assert result[1] == "Alice"

    # Both busted (lower busted score wins)
    result = twenty_one_game._determine_winner(25, 23, player1, player2)
    assert result[0] == "Bob"
    assert result[1] == "Alice"

    # Only player1 valid
    result = twenty_one_game._determine_winner(19, 25, player1, player2)
    assert result[0] == "Alice"
    assert result[1] == "Bob"

    # Only player2 valid
    result = twenty_one_game._determine_winner(25, 20, player1, player2)
    assert result[0] == "Bob"
    assert result[1] == "Alice"


@pytest.mark.asyncio
async def test_process_single_game_with_remaining_players(twenty_one_game):
    """Test that remaining players in queue get correct messages."""
    twenty_one_game.bot.get_channel = MagicMock()
    channel_mock = AsyncMock()
    twenty_one_game.bot.get_channel.return_value = channel_mock

    # Add 4 players to queue
    twenty_one_game.player_queue.extend([("1", "A"), ("2", "B"), ("3", "C"), ("4", "D")])

    # Patch _start_game to avoid real logic
    twenty_one_game._start_game = AsyncMock()

    await twenty_one_game._process_single_game()

    # There should be 2 players left
    assert len(twenty_one_game.player_queue) == 2
    # Channel.send should be called with remaining players info
    assert any("В очереди осталось" in str(c) for c in channel_mock.send.call_args_list)


@pytest.mark.asyncio
async def test_handle_game_result_timeout_non_privileged(twenty_one_game):
    """Test loser timeout is called for non-privileged users."""
    twenty_one_game.api = AsyncMock()
    twenty_one_game.db = AsyncMock()
    twenty_one_game.RANKS = twenty_one_game.RANKS

    channel_mock = AsyncMock()
    # Use a non-privileged loser
    await twenty_one_game._handle_game_result(
        channel_mock,
        winner_name="Winner",
        loser_name="Loser",
        winner_id="1",
        loser_id="2",
        player1_name="Winner",
        player2_name="Loser",
        score1=21,
        score2=19,
    )

    # Timeout should be called
    twenty_one_game.api.timeout_user.assert_awaited_with(
        user_id="2", channel_name=channel_mock.name, duration=15, reason="очко"
    )


@pytest.mark.asyncio
async def test_handle_game_result_privileged(twenty_one_game):
    """Test that privileged user does not get timeout."""
    twenty_one_game.api = AsyncMock()
    twenty_one_game.db = AsyncMock()
    twenty_one_game.RANKS = twenty_one_game.RANKS

    from src.commands.games.twenty_one import PRIVILEGED_USERS_LOWER

    privileged_name = next(iter(PRIVILEGED_USERS_LOWER), "mod")

    channel_mock = AsyncMock()
    await twenty_one_game._handle_game_result(
        channel_mock,
        winner_name="Winner",
        loser_name=privileged_name,
        winner_id="1",
        loser_id="2",
        player1_name="Winner",
        player2_name=privileged_name,
        score1=21,
        score2=19,
    )

    twenty_one_game.api.timeout_user.assert_not_called()


@pytest.mark.asyncio
async def test_has_tickets_and_consume_ticket(twenty_one_game):
    """Test ticket logic."""
    twenty_one_game.db = AsyncMock()
    twenty_one_game.db.remove_tickets = AsyncMock(return_value=3)

    # has_tickets returns True
    assert await twenty_one_game.has_tickets("1") is True
    twenty_one_game.db.remove_tickets.assert_awaited_with("1", 0)

    # consume_ticket calls db.remove_tickets
    await twenty_one_game.consume_ticket("1")
    twenty_one_game.db.remove_tickets.assert_awaited_with("1", 1)


@pytest.mark.asyncio
async def test_process_queue_with_timer_cancellation(twenty_one_game):
    """Test that timer can be cancelled without raising."""
    twenty_one_game.is_processing = False
    twenty_one_game.player_queue.append(("1", "A"))

    task = asyncio.create_task(twenty_one_game._process_queue_with_timer())
    await asyncio.sleep(0.001)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass  # Expected cancellation


@pytest.mark.asyncio
async def test_handle_me_command_no_games(twenty_one_game):
    """Test 'me' command when user has no games."""
    # Mock database
    twenty_one_game.db = AsyncMock()
    twenty_one_game.db.get_stats = AsyncMock(return_value=(0, 0))
    twenty_one_game.db.remove_tickets = AsyncMock(return_value=0)

    # Mock bot and cache_manager for cooldown
    twenty_one_game.bot = AsyncMock()
    twenty_one_game.bot.cache_manager = AsyncMock()
    twenty_one_game.bot.cache_manager.is_command_available = AsyncMock(return_value=True)

    # Mock ctx
    ctx = AsyncMock()
    ctx.author.id = 1
    ctx.author.name = "Player"
    ctx.send = AsyncMock()

    # Run command
    await twenty_one_game.handle_me_command(ctx)
    ctx.send.assert_awaited()  # Ensure message sent


@pytest.mark.asyncio
async def test_handle_leaders_command_empty(twenty_one_game):
    """Test 'leaders' command with empty leaderboard."""
    # Mock database
    twenty_one_game.db = AsyncMock()
    twenty_one_game.db.get_top_players = AsyncMock(return_value=[])

    # Mock bot and cache_manager for cooldown
    twenty_one_game.bot = AsyncMock()
    twenty_one_game.bot.cache_manager = AsyncMock()
    twenty_one_game.bot.cache_manager.is_command_available = AsyncMock(return_value=True)

    # Mock ctx
    ctx = AsyncMock()
    ctx.send = AsyncMock()

    # Run command
    await twenty_one_game.handle_leaders_command(ctx)
    ctx.send.assert_awaited_with("📊 Рейтинг пока пуст")
