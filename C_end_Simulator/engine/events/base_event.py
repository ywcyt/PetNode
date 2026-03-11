"""
BaseEvent —— 事件抽象基类

事件有三个阶段 (phase):  onset → peak → recovery
强度曲线 intensity 在 [0, 1] 之间变化。

子类需覆盖:
  - name, base_duration_days
  - vital_effect(intensity) → dict  返回瞬时值叠加量
  - steps_multiplier(intensity) → float  返回步数倍率
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class EventPhase(enum.Enum):
    ONSET = "onset"
    PEAK = "peak"
    RECOVERY = "recovery"


@dataclass
class BaseEvent:
    """
    事件基类

    Parameters
    ----------
    duration_days : int
        总持续天数（已经过 trait severity multiplier 修正）
    severity : float
        严重度倍率（1.0 为正常，>1.0 更严重）
    """

    name: str = "base_event"
    base_duration_days: int = 7
    duration_days: int = 7
    severity: float = 1.0
    day_index: int = 0

    # 阶段占比: onset 20%, peak 40%, recovery 40%
    onset_ratio: float = 0.2
    peak_ratio: float = 0.4

    @property
    def phase(self) -> EventPhase:
        progress = self.day_index / max(self.duration_days, 1)
        if progress < self.onset_ratio:
            return EventPhase.ONSET
        elif progress < self.onset_ratio + self.peak_ratio:
            return EventPhase.PEAK
        else:
            return EventPhase.RECOVERY

    @property
    def intensity(self) -> float:
        """
        强度曲线 [0, 1]:
        - onset:    线性上升  0 → 1
        - peak:     保持 1.0
        - recovery: 线性下降  1 → 0
        """
        progress = self.day_index / max(self.duration_days, 1)
        phase = self.phase
        if phase == EventPhase.ONSET:
            return progress / max(self.onset_ratio, 1e-9)
        elif phase == EventPhase.PEAK:
            return 1.0
        else:
            rec_start = self.onset_ratio + self.peak_ratio
            rec_len = 1.0 - rec_start
            return max(0.0, 1.0 - (progress - rec_start) / max(rec_len, 1e-9))

    @property
    def is_finished(self) -> bool:
        return self.day_index >= self.duration_days

    def advance_day(self) -> None:
        self.day_index += 1

    def vital_effect(self) -> dict:
        """返回对瞬时值的叠加 {heart_rate: +x, resp_rate: +y, temperature: +z}"""
        return {}

    def steps_multiplier_value(self) -> float:
        """返回 Δsteps 的乘法倍率"""
        phase = self.phase
        if phase == EventPhase.ONSET:
            return 0.8
        elif phase == EventPhase.PEAK:
            return 0.3
        else:
            recovery_progress = 0.0
            rec_start = self.onset_ratio + self.peak_ratio
            rec_len = 1.0 - rec_start
            progress = self.day_index / max(self.duration_days, 1)
            if rec_len > 0:
                recovery_progress = (progress - rec_start) / rec_len
            return 0.6 + 0.4 * recovery_progress

    def gps_sigma_multiplier(self) -> float:
        """返回 GPS σ 的乘法倍率"""
        return max(0.1, 1.0 - self.intensity * 0.5)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(day={self.day_index}/{self.duration_days}, "
            f"phase={self.phase.value}, intensity={self.intensity:.2f})"
        )
