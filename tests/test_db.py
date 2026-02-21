from collections.abc import AsyncGenerator

import pytest

from src.db.database import Base, Database, PlayerStats


@pytest.fixture
async def db() -> AsyncGenerator[Database]:
    """
    Fixture to provide an in-memory SQLite database for testing.

    Returns:
        Database: An instance of the Database class connected to in-memory SQLite.
    """
    # Create an in-memory SQLite database
    database = Database("sqlite+aiosqlite:///:memory:")

    # Create all tables
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield database

    # Dispose engine after tests
    await database.engine.dispose()


@pytest.mark.asyncio
async def test_update_and_get_stats(db: Database) -> None:
    """Test updating and retrieving player statistics."""
    # Add a new player with a win
    wins, losses = await db.update_stats("twitch1", "User1", win=True)
    assert wins == 1
    assert losses == 0

    # Add a new player with a loss
    wins, losses = await db.update_stats("twitch2", "User2", win=False)
    assert wins == 0
    assert losses == 1

    # Retrieve stats
    win, loose = await db.get_stats("twitch1")
    assert win == 1
    assert loose == 0

    win, loose = await db.get_stats("twitch2")
    assert win == 0
    assert loose == 1


@pytest.mark.asyncio
async def test_get_top_players(db: Database) -> None:
    """Test retrieving top players ordered by wins."""
    # Populate sample data
    await db.update_stats("t1", "Alice", True)
    await db.update_stats("t1", "Alice", True)  # Alice now has 2 wins
    await db.update_stats("t2", "Bob", True)  # Bob has 1 win
    await db.update_stats("t3", "Charlie", False)  # Charlie has 0 wins

    # Retrieve top 2 players
    top_players = await db.get_top_players(limit=2)

    # Validate order and stats
    assert top_players[0][0] == "Alice"
    assert top_players[0][1] == 2
    assert top_players[1][0] == "Bob"
    assert top_players[1][1] == 1


@pytest.mark.asyncio
async def test_player_rank(db: Database) -> None:
    """Test retrieving player ranks based on win counts."""
    # Populate sample data
    await db.update_stats("u1", "Alice", True)  # Alice 1 win
    await db.update_stats("u1", "Alice", True)  # Alice 2 wins
    await db.update_stats("u2", "Bob", True)  # Bob 1 win
    await db.update_stats("u3", "Charlie", False)  # Charlie 0 wins

    # Retrieve player ranks
    top_players = await db.get_top_players(limit=3)
    wins_order = [player[1] for player in top_players]
    assert wins_order == sorted(wins_order, reverse=True)
    # Validate ranks
    assert top_players[0][0] == "Alice"
    assert top_players[0][1] == 2
    assert top_players[1][0] == "Bob"
    assert top_players[1][1] == 1
    assert top_players[2][0] == "Charlie"
    assert top_players[2][1] == 0


@pytest.mark.asyncio
async def test_update_existing_player(db: Database) -> None:
    """Test updating statistics for an existing player."""
    # Create a new player with a win
    await db.update_stats("p1", "Player1", True)

    # Update player with a loss
    wins, losses = await db.update_stats("p1", "Player1", False)

    assert wins == 1
    assert losses == 1


@pytest.mark.asyncio
async def test_get_stats_nonexistent_player(db: Database) -> None:
    """
    Test retrieving stats for a player that does not exist.

    Should return (0, 0).
    """
    wins, losses = await db.get_stats("unknown")
    assert wins == 0
    assert losses == 0


@pytest.mark.asyncio
async def test_win_rate_calculation() -> None:
    """Test the win_rate method in the PlayerStats model."""
    player = PlayerStats(twitch_id="x", username="Test", wins=3, losses=1)
    assert player.win_rate() == 75.0

    player = PlayerStats(twitch_id="y", username="Test2", wins=0, losses=0)
    assert player.win_rate() == 0.0


@pytest.mark.asyncio
async def test_add_and_remove_tickets(db: Database):
    """Test adding and removing tickets for a player in the database."""
    # Add 5 tickets to player1
    tickets = await db.add_tickets("player1", "Alice", 5)
    assert tickets == 5

    # Add 3 more tickets to player1 (total should be 8)
    tickets = await db.add_tickets("player1", "Alice", 3)
    assert tickets == 8

    # Remove 4 tickets (should leave 4 remaining)
    tickets = await db.remove_tickets("player1", 4)
    assert tickets == 4

    # Try to remove 10 tickets (only 4 remaining, should return 0)
    tickets = await db.remove_tickets("player1", 10)
    assert tickets == 0

    # Try to remove tickets for a non-existent player (should return 0)
    tickets = await db.remove_tickets("unknown", 1)
    assert tickets == 0
