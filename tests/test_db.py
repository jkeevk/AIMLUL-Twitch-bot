import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.db.database import Base, Database, PlayerStats


@pytest.fixture
async def db() -> Database:
    """
    Fixture to provide an in-memory SQLite database for testing.

    Returns:
        Database: An instance of the Database class connected to in-memory SQLite.
    """
    # Create in-memory SQLite async engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Configure sessionmaker for async sessions
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Instantiate Database with proper session
    database = Database(dsn="sqlite+aiosqlite:///:memory:")
    database.engine = engine
    database.async_session = async_session

    yield database

    # Dispose engine after tests
    await engine.dispose()


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
    await db.update_stats("u1", "User1", True)
    await db.update_stats("u1", "User1", True)  # User1 wins 2 games
    await db.update_stats("u2", "User2", True)  # User2 wins 1 game
    await db.update_stats("u3", "User3", False)  # User3 has 0 wins

    # Retrieve player ranks
    rank_u1 = await db.get_player_rank("u1")
    rank_u2 = await db.get_player_rank("u2")
    rank_u3 = await db.get_player_rank("u3")

    # Validate ranks
    assert rank_u1 == 1
    assert rank_u2 == 2
    assert rank_u3 == 3


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
