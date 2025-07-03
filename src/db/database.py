import logging
from contextlib import asynccontextmanager
from sqlalchemy import select, desc, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .models import Base, PlayerStats

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, dsn: str):
        self.engine = create_async_engine(dsn, echo=False, future=True)
        self.async_session = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        logger.info("✅ Database engine initialized")

    async def connect(self):
        """Подключается к базе и создает таблицы, если их нет"""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("🔄 Database tables created/verified")
        except SQLAlchemyError as e:
            logger.error(f"🚨 Database connection error: {e}")
            raise

    async def close(self):
        try:
            await self.engine.dispose()
            logger.info("🔌 Database connection closed")
        except SQLAlchemyError as e:
            logger.error(f"🚨 Error closing database: {e}")

    @asynccontextmanager
    async def session_scope(self):
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"🚨 Database error: {e}")
                raise

    async def update_stats(self, twitch_id: str, username: str, win: bool):
        try:
            async with self.session_scope() as session:
                result = await session.execute(
                    select(PlayerStats).where(PlayerStats.twitch_id == twitch_id)
                )
                player = result.scalars().first()

                if player:
                    if win:
                        player.wins += 1
                    else:
                        player.losses += 1
                    logger.info(
                        f"📝 Обновлена статистика для {username}: +{'победа' if win else 'поражение'}"
                    )
                else:
                    player = PlayerStats(
                        twitch_id=twitch_id,
                        username=username,
                        wins=1 if win else 0,
                        losses=0 if win else 1,
                    )
                    session.add(player)
                    logger.info(f"🆕 Создана запись для {username}")

                await session.flush()
                return player.wins, player.losses

        except SQLAlchemyError as e:
            logger.error(f"🚨 Update stats error: {e}", exc_info=True)
            return 0, 0

    async def get_stats(self, twitch_id: str):
        try:
            async with self.session_scope() as session:
                result = await session.execute(
                    select(PlayerStats).where(PlayerStats.twitch_id == twitch_id)
                )
                player = result.scalars().first()

                if player:
                    return player.wins, player.losses
                return 0, 0

        except SQLAlchemyError as e:
            logger.error(f"🚨 Get stats error: {e}")
            return 0, 0

    async def get_top_players(self, limit: int = 3):
        """Возвращает топ игроков по количеству побед"""
        try:
            async with self.session_scope() as session:
                stmt = select(PlayerStats).order_by(desc(PlayerStats.wins)).limit(limit)
                result = await session.execute(stmt)
                top_players = result.scalars().all()

                return [
                    (player.username, player.wins, player.losses)
                    for player in top_players
                ]

        except SQLAlchemyError as e:
            logger.error(f"🚨 Get top players error: {e}")
            return []

    async def get_player_rank(self, twitch_id: str):
        """Возвращает позицию игрока в общем рейтинге"""
        try:
            async with self.session_scope() as session:
                subquery = (
                    select(
                        PlayerStats.twitch_id,
                        func.rank()
                        .over(order_by=desc(PlayerStats.wins))
                        .label("position"),
                    )
                ).subquery()

                stmt = select(subquery.c.position).where(
                    subquery.c.twitch_id == twitch_id
                )

                result = await session.execute(stmt)
                rank = result.scalar()

                return rank if rank else None

        except SQLAlchemyError as e:
            logger.error(f"🚨 Get player rank error: {e}")
            return None
