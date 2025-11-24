import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import desc, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base, PlayerStats

logger = logging.getLogger(__name__)


class Database:
    """Database management class for handling player statistics."""

    def __init__(self, dsn: str) -> None:
        """
        Initialize database connection.

        Args:
            dsn: Database connection string
        """
        self.engine = create_async_engine(dsn, echo=False, future=True)
        self.async_session = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)
        logger.info("Database engine initialized")

    async def connect(self) -> None:
        """Connect to a database and create tables if they don't exist."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created/verified")
        except SQLAlchemyError as e:
            logger.error(f"Database connection error: {e}")
            raise

    async def close(self) -> None:
        """Close database connection."""
        try:
            await self.engine.dispose()
            logger.info("Database connection closed")
        except SQLAlchemyError as e:
            logger.error(f"Error closing database: {e}")

    @asynccontextmanager
    async def session_scope(self) -> AsyncGenerator[AsyncSession]:
        """
        Provide a transactional scope around a series of operations.

        Yields:
            AsyncSession: Database session object

        Raises:
            SQLAlchemyError: If database operation fails
        """
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Database transaction error: {e}")
                raise

    async def update_stats(self, twitch_id: str, username: str, win: bool) -> tuple[int, int]:
        """
        Update player statistics with win/loss.

        Args:
            twitch_id: Player's Twitch ID
            username: Player's username
            win: True if player won, False if lost

        Returns:
            Tuple of (wins, losses) count for the player
        """
        try:
            async with self.session_scope() as session:
                result = await session.execute(select(PlayerStats).where(PlayerStats.twitch_id == twitch_id))
                player = result.scalars().first()

                if player:
                    if win:
                        player.wins += 1
                    else:
                        player.losses += 1
                    logger.info(f"Updated stats for {username}: {'win' if win else 'loss'}")
                else:
                    player = PlayerStats(
                        twitch_id=twitch_id,
                        username=username,
                        wins=1 if win else 0,
                        losses=0 if win else 1,
                    )
                    session.add(player)
                    logger.info(f"Created new record for {username}")

                await session.flush()
                return player.wins, player.losses

        except SQLAlchemyError as e:
            logger.error(f"Update stats error: {e}", exc_info=True)
            return 0, 0

    async def get_stats(self, twitch_id: str) -> tuple[int, int]:
        """
        Retrieve player statistics.

        Args:
            twitch_id: Player's Twitch ID

        Returns:
            Tuple of (wins, losses) for the player
        """
        try:
            async with self.session_scope() as session:
                result = await session.execute(select(PlayerStats).where(PlayerStats.twitch_id == twitch_id))
                player = result.scalars().first()

                if player:
                    return player.wins, player.losses
                return 0, 0

        except SQLAlchemyError as e:
            logger.error(f"Get stats error: {e}")
            return 0, 0

    async def get_top_players(self, limit: int = 3) -> list[tuple[str, int, int]]:
        """
        Retrieve top players by win count.

        Args:
            limit: Number of top players to return

        Returns:
            List of tuples containing (username, wins, losses) for each player
        """
        try:
            async with self.session_scope() as session:
                stmt = select(PlayerStats).order_by(desc(PlayerStats.wins)).limit(limit)
                result = await session.execute(stmt)
                top_players = result.scalars().all()

                return [(player.username, player.wins, player.losses) for player in top_players]

        except SQLAlchemyError as e:
            logger.error(f"Get top players error: {e}")
            return []

    async def get_player_rank(self, twitch_id: str) -> int | None:
        """
        Get player's rank position based on wins.

        Args:
            twitch_id: Player's Twitch ID

        Returns:
            Player's rank position or None if not found
        """
        try:
            async with self.session_scope() as session:
                subquery = (
                    select(
                        PlayerStats.twitch_id,
                        func.rank().over(order_by=desc(PlayerStats.wins)).label("position"),
                    )
                ).subquery()

                stmt = select(subquery.c.position).where(subquery.c.twitch_id == twitch_id)
                result = await session.execute(stmt)
                rank = result.scalar()

                return rank if rank else None

        except SQLAlchemyError as e:
            logger.error(f"Get player rank error: {e}")
            return None
