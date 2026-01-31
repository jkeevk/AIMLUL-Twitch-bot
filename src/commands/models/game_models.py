import random
import time
from dataclasses import dataclass


@dataclass
class GameRank:
    """
    Game ranking system based on win thresholds.

    Maps win counts to rank names with automatic threshold detection.
    """

    thresholds: dict[int, str]

    def get_rank(self, wins: int) -> str:
        """
        Get player's rank based on win count.

        Args:
            wins: Number of player's wins

        Returns:
            Rank name corresponding to the win count
        """
        sorted_thresholds = sorted(self.thresholds.keys(), reverse=True)
        for threshold in sorted_thresholds:
            if wins >= threshold:
                return self.thresholds[threshold]
        return self.thresholds[0]


@dataclass
class CollectorConfig:
    """
    Configuration for participant collectors.

    Defines behavior for collecting multiple participants before triggering actions.
    """

    name: str
    reset_time: int
    reason: str
    timeout_message: str
    duration: int
    required_participants: int = 3


class BaseCollector:
    """
    Base collector implementation for gathering multiple participants.

    Manages participant lists, automatic reset timers, and random selection
    for timeout-based game mechanics.
    """

    def __init__(self, config: CollectorConfig):
        """
        Initialize collector with configuration.

        Args:
            config: Collector configuration parameters
        """
        self.config = config
        self.participants: list[tuple[str, str]] = []
        self.last_added: float = 0.0

    def add(self, user_id: str, user_name: str) -> bool:
        """
        Add participant to the collection.

        Args:
            user_id: Twitch user ID
            user_name: Twitch display name

        Returns:
            True if participant was added, False if participant already exists
        """
        if any(uid == user_id for uid, _ in self.participants):
            return False

        self.participants.append((user_id, user_name))
        self.last_added = time.time()

        return True

    def reset(self) -> None:
        """Reset collector by clearing all participants."""
        self.participants = []

    def should_reset(self) -> bool:
        """
        Check if collector should reset due to inactivity.

        Returns:
            True if the reset time threshold exceeded, False otherwise
        """
        return time.time() - self.last_added > self.config.reset_time

    def is_full(self) -> bool:
        """
        Check if collector has required number of participants.

        Returns:
            True if participant count meets requirement, False otherwise
        """
        return len(self.participants) >= self.config.required_participants

    def get_random(self) -> tuple[str, str] | None:
        """
        Get random participant from the collection.

        Returns:
            Tuple of (user_id, user_name) or None if no participants
        """
        return random.choice(self.participants) if self.participants else None
