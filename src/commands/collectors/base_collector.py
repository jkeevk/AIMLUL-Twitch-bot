import random
import time
from typing import List, Tuple


class BaseCollector:
    def __init__(self, reset_time: int = 300):
        self.participants: List[Tuple[str, str]] = []
        self.reset_time = reset_time
        self.last_added = 0

    def add(self, user_id: str, user_name: str) -> bool:
        """Добавляет участника в сбор. Возвращает True если добавлен, False если уже есть"""
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
        return time.time() - self.last_added > self.reset_time

    def is_full(self) -> bool:
        """Проверяет заполненность сборщика"""
        return len(self.participants) >= 3

    def get_last(self):
        """Возвращает последнего добавленного участника"""
        return self.participants[-1] if self.participants else None

    def get_random(self):
        """Возвращает случайного добавленного участника"""
        return random.choice(self.participants) if self.participants else None
