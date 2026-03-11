"""FeverEvent —— 发烧事件"""

from .base_event import BaseEvent


class FeverEvent(BaseEvent):
    """
    发烧：
    - 基础持续 7 天
    - 体温升高，心率升高，呼吸频率升高
    - 步数显著减少
    """

    name: str = "fever"
    base_duration_days: int = 7

    def vital_effect(self) -> dict:
        i = self.intensity * self.severity
        return {
            "heart_rate": 15.0 * i,
            "resp_rate": 6.0 * i,
            "temperature": 1.5 * i,
        }

    def steps_multiplier_value(self) -> float:
        base = super().steps_multiplier_value()
        return base * max(0.2, 1.0 - 0.3 * self.severity)
