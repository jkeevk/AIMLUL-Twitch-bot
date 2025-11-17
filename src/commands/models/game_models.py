from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import time
import random


@dataclass
class GameRank:
    """Модель ранга в игре"""
    thresholds: Dict[int, str]

    def get_rank(self, wins: int) -> str:
        """Возвращает текущий ранг по количеству побед"""
        sorted_thresholds = sorted(self.thresholds.keys(), reverse=True)
        for threshold in sorted_thresholds:
            if wins >= threshold:
                return self.thresholds[threshold]
        return self.thresholds[0]


@dataclass
class CollectorConfig:
    """Конфигурация коллектора"""
    name: str
    reset_time: int
    reason: str
    timeout_message: str
    duration: int
    required_participants: int = 3


class BaseCollector:
    """Базовая реализация коллектора"""

    def __init__(self, config: CollectorConfig):
        self.config = config
        self.participants: List[Tuple[str, str]] = []
        self.last_added = 0

    def add(self, user_id: str, user_name: str) -> bool:
        """Добавляет участника в сбор"""
        if any(uid == user_id for uid, _ in self.participants):
            return False

        self.participants.append((user_id, user_name))
        self.last_added = time.time()
        return True

    def reset(self) -> None:
        """Сбрасывает сборщик"""
        self.participants = []

    def should_reset(self) -> bool:
        """Проверяет необходимость сброса по времени"""
        return time.time() - self.last_added > self.config.reset_time

    def is_full(self) -> bool:
        """Проверяет заполненность сборщика"""
        return len(self.participants) >= self.config.required_participants

    def get_random(self):
        """Возвращает случайного добавленного участника"""
        return random.choice(self.participants) if self.participants else None