from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class PlayerStats(Base):
    __tablename__ = "player_stats"

    id = Column(Integer, primary_key=True)
    twitch_id = Column(String(255), unique=True, nullable=False)
    username = Column(String(255), nullable=False)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def win_rate(self) -> float:
        total = self.wins + self.losses
        return (self.wins / total) * 100 if total > 0 else 0.0

    def __repr__(self):
        return f"<PlayerStats(username={self.username}, wins={self.wins}, losses={self.losses})>"
