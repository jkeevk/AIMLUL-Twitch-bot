from .base_collector import BaseCollector


class ApplecatCollector(BaseCollector):
    def __init__(self):
        super().__init__(reset_time=300)

    @property
    def reason(self) -> str:
        return "не бегать"

    @property
    def timeout_message(self) -> str:
        return "@{target_name}, не бегать! Applecatrunt"

    @property
    def duration(self) -> int:
        return 60
