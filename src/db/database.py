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
        Update player's win/loss statistics.

        If the player does not exist, a new record is created.

        Args:
            twitch_id (str): Twitch ID of the player.
            username (str): Username of the player.
            win (bool): True if the player won, False if lost.

        Returns:
            tuple[int, int]: Updated (wins, losses) for the player.

        Notes:
            Returns (0, 0) if a database error occurs.
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
        Retrieve the win/loss statistics for a player.

        Args:
            twitch_id (str): The Twitch ID of the player.

        Returns:
            tuple[int, int]: A tuple (wins, losses) representing the player's statistics.
                             Returns (0, 0) if the player is not found or if an error occurs.
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
        Retrieve a list of the top players by number of wins.

        Args:
            limit (int): The maximum number of top players to return. Default to 3 if not specified.

        Returns:
            list[tuple[str, int, int]]: A list of tuples, each containing (username, wins, losses)
                                        for a top player. Returns an empty list if an error occurs.
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
        Add tickets to a player. Creates a new player record if none exists.

        Args:
            twitch_id (str): Twitch ID of the player.
            username (str): Player's username.
            amount (int): Number of tickets to add.

        Returns:
            int: Total tickets after addition. Returns 0 on error.
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
        Remove tickets from a player. The ticket count will not go below zero.

        Args:
            twitch_id (str): Twitch ID of the player.
            amount (int): Number of tickets to remove.

        Returns:
            int: Total tickets after removal. Returns 0 if player not found or on error.
        """
        try:
            async with self.session_scope() as session:
                result = await session.execute(select(PlayerStats).where(PlayerStats.twitch_id == twitch_id))
                player = result.scalars().first()

                if not player:
                    return 0

                current_tickets = player.tickets
                new_tickets = max(current_tickets - amount, 0)
                player.tickets = new_tickets

                await session.flush()
                return new_tickets

        except SQLAlchemyError as e:
            logger.error(f"Remove tickets error: {e}", exc_info=True)
            return 0

    async def get_scheduled_offline(self, date: datetime.date) -> ScheduledOffline | None:
        """
        Get the scheduled offline record for a specific date.

        Args:
            date (datetime.date): The date to fetch the offline record for.

        Returns:
            ScheduledOffline | None: The scheduled offline record if exists, else None.
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
        Create or update a scheduled offline record.

        Args:
            date (datetime.date): Date of the scheduled offline.
            sent_message (bool): Whether the offline message has been sent. Defaults to True.
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
