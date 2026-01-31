import datetime
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base, PlayerStats, ScheduledOffline

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

    async def add_tickets(self, twitch_id: str, username: str, amount: int) -> int:
        """
        Add tickets to a player, creating a record if needed.

        Args:
            twitch_id: Twitch ID of the player
            username: Username of the player
            amount: Number of tickets to add

        Returns:
            Total tickets after addition
        """
        try:
            async with self.session_scope() as session:
                result = await session.execute(select(PlayerStats).where(PlayerStats.twitch_id == twitch_id))
                player = result.scalars().first()

                if not player:
                    player = PlayerStats(twitch_id=twitch_id, username=username, tickets=amount)
                    session.add(player)
                else:
                    player.tickets += amount

                await session.flush()
                return player.tickets

        except SQLAlchemyError as e:
            logger.error(f"Add tickets error: {e}", exc_info=True)
            return 0

    async def remove_tickets(self, twitch_id: str, amount: int) -> int:
        """
        Remove tickets from a player. Tickets will not go below zero.

        Args:
            twitch_id: Twitch ID of the player
            amount: Number of tickets to remove

        Returns:
            Total tickets after removal (0 if player not found or error)
        """
        try:
            async with self.session_scope() as session:
                result = await session.execute(select(PlayerStats).where(PlayerStats.twitch_id == twitch_id))
                player = result.scalars().first()

                if not player:
                    return 0

                player.tickets = max(player.tickets - amount, 0)

                await session.flush()
                return player.tickets

        except SQLAlchemyError as e:
            logger.error(f"Remove tickets error: {e}", exc_info=True)
            return 0

    async def get_scheduled_offline(self, date: datetime.date) -> ScheduledOffline | None:
        """
        Retrieve the scheduled offline record for a specific date.

        Args:
            date: The date for which to fetch the scheduled offline record.

        Returns:
            The ScheduledOffline object if found, otherwise None.
        """
        try:
            async with self.session_scope() as session:
                result = await session.execute(select(ScheduledOffline).where(ScheduledOffline.date == date))
                return result.scalars().first()
        except SQLAlchemyError as e:
            logger.error(f"Get scheduled offline error: {e}", exc_info=True)
            return None

    async def set_scheduled_offline(self, date: datetime.date, sent_message: bool = True) -> None:
        """
        Create or update the scheduled offline record for a given date.

        Args:
            date: The date for which to set the scheduled offline record.
            sent_message: Whether the offline message has been sent (default True).

        Returns:
            None
        """
        try:
            async with self.session_scope() as session:
                record = await self.get_scheduled_offline(date)
                if not record:
                    record = ScheduledOffline(date=date, sent_message=sent_message)
                    session.add(record)
                else:
                    record.sent_message = sent_message
                await session.flush()
        except SQLAlchemyError as e:
            logger.error(f"Set scheduled offline error: {e}", exc_info=True)
