from .base_collector import BaseCollector


class GnomeCollector(BaseCollector):
    def __init__(self):
        super().__init__(reset_time=300)
    @property
    def reason(self) -> str:
        return "гном"

    @property
    def timeout_message(self) -> str:
        return "@{target_name}, попался гном Angry 👉🚪"

    @property
    def duration(self) -> int:
        return 60
