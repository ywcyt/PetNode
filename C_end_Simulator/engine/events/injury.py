"""InjuryEvent —— 受伤/跛行事件"""

from .base_event import BaseEvent, EventPhase


class InjuryEvent(BaseEvent):
    """
    受伤：
    - 基础持续 10 天
    - 心率略升，体温略升
    - 步数在 peak 阶段几乎为 0
    - GPS 偏移在 peak 阶段几乎为 0
    """

    name: str = "injury"
    base_duration_days: int = 10

    def vital_effect(self) -> dict:
        i = self.intensity * self.severity
        return {
            "heart_rate": 8.0 * i,
            "resp_rate": 2.0 * i,
            "temperature": 0.5 * i,
        }

    def steps_multiplier_value(self) -> float:
        phase = self.phase
        if phase == EventPhase.PEAK:
            return 0.05 / max(self.severity, 1.0)
        elif phase == EventPhase.ONSET:
            return 0.4
        else:
            recovery_progress = 0.0
            rec_start = self.onset_ratio + self.peak_ratio
            rec_len = 1.0 - rec_start
            progress = self.day_index / max(self.duration_days, 1)
            if rec_len > 0:
                recovery_progress = (progress - rec_start) / rec_len
            return 0.3 + 0.7 * recovery_progress

    def gps_sigma_multiplier(self) -> float:
        if self.phase == EventPhase.PEAK:
            return 0.05
        return max(0.1, 1.0 - self.intensity * 0.7)
