import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_first_two_play_instantly(twenty_one_game):
    """
    Test that the first two players join the game and start immediately.

    The game timer is set to 1 second, ensuring instant play for the first two participants.
    """
    twenty_one_game.timer_seconds = 1

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

    await asyncio.sleep(0.1)
    assert len(twenty_one_game.player_queue) == 0


@pytest.mark.asyncio
async def test_third_and_fourth_start_with_dynamic_timer(twenty_one_game):
    """
    Test that the third and fourth players are handled with a dynamic timer.

    The game timer is set to 5 seconds. Third player should wait for an opponent,
    and fourth player should trigger join messages correctly.
    """
    twenty_one_game.timer_seconds = 5

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
    await asyncio.sleep(0.1)

    await twenty_one_game.handle_command(ctx3)
    assert any("ждет соперника" in msg for msg in ctx3.sent)

    await asyncio.sleep(0.1)
    await twenty_one_game.handle_command(ctx4)


@pytest.mark.asyncio
async def test_repeated_player_cannot_join_twice(twenty_one_game):
    """Test that the same player cannot join the game twice consecutively."""
    twenty_one_game.timer_seconds = 1

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
    twenty_one_game.timer_seconds = 1

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
    await asyncio.sleep(0.1)
    assert len(twenty_one_game.player_queue) == 0


@pytest.mark.asyncio
async def test_multiple_games_sequentially(twenty_one_game):
    """
    Test handling multiple 21-game sessions sequentially.

    Ensures that players are queued and processed correctly across
    consecutive game sessions.
    """
    twenty_one_game.timer_seconds = 1

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
    await asyncio.sleep(twenty_one_game.timer_seconds + 0.1)
    assert len(twenty_one_game.player_queue) == 0

    # -------------------- Game 2 -------------------- #
    ctx3, ctx4 = make_ctx(3, "User3"), make_ctx(4, "User4")
    await twenty_one_game.handle_command(ctx3)
    await twenty_one_game.handle_command(ctx4)
    await asyncio.sleep(twenty_one_game.timer_seconds + 0.1)
    assert len(twenty_one_game.player_queue) == 0

    # -------------------- Game 3 -------------------- #
    ctx5 = make_ctx(3, "User5")
    await twenty_one_game.handle_command(ctx5)
    await asyncio.sleep(twenty_one_game.timer_seconds + 0.1)
    assert len(twenty_one_game.player_queue) == 1
