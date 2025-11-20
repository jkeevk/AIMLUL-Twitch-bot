from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class PlayerStats(Base):
    """
    Database model for storing player statistics in Twitch bot.

    Tracks wins, losses, and provides calculated metrics like win rate.
    Includes timestamps for creation and last update.
    """

    __tablename__ = "player_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    twitch_id = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=False, index=True)
    wins = Column(Integer, default=0, nullable=False)
    losses = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def win_rate(self) -> float:
        """
        Calculate player's win rate percentage.

        Returns:
            Win rate as percentage (0.0 to 100.0), returns 0.0 if no games played
        """
        total_games = self.wins + self.losses
        if total_games == 0:
            return 0.0
        return (self.wins / total_games) * 100

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
