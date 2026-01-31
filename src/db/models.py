from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


class PlayerStats(Base):
    """
    Represents player statistics in the database.

    Attributes:
        id (int): Primary key.
        twitch_id (str): Unique Twitch ID of the player.
        username (str): Player's username.
        wins (int): Number of wins.
        losses (int): Number of losses.
        created_at (datetime): Record creation timestamp.
        updated_at (datetime): Record last update timestamp.
    """

    __tablename__ = "player_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    twitch_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tickets: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def win_rate(self) -> float:
        """
        Calculate the player's win rate as a percentage.

        Returns:
            float: Win rate percentage (0.0 if no games played).
        """
        total_games: int = self.wins + self.losses
        if total_games == 0:
            return 0.0
        return (self.wins / total_games) * 100.0

    def __repr__(self) -> str:
        """
        Official string representation of the model.

        Returns:
            String representation showing key attributes
        """
        return (
            f"PlayerStats("
            f"id={self.id}, "
            f"username='{self.username}', "
            f"wins={self.wins}, "
            f"losses={self.losses}, "
            f"win_rate={self.win_rate():.1f}%"
            f")"
        )


class ScheduledOffline(Base):
    """
    Represents a scheduled offline record for the bot.

    Each record stores the last date the bot was automatically disabled
    according to the schedule. This helps prevent sending repeated offline
    messages on restarts.

    Attributes:
        id (int): Primary key.
        date (datetime): The date the bot was scheduled to go offline.
        sent_message (bool): Whether the offline message has already been sent for this date.
    """

    __tablename__ = "scheduled_offline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    sent_message: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        """
        Return a string representation of the ScheduledOffline object.

        Returns:
            str: A string showing the id, date, and sent_message flag.
        """
        return f"ScheduledOffline(id={self.id}, date={self.date}, sent_message={self.sent_message})"
