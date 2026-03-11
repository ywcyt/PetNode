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
    """
    事件的三个阶段枚举。

    事件生命周期：ONSET（发病/恶化期）→ PEAK（高峰期）→ RECOVERY（恢复期）。
    阶段占比由 onset_ratio 和 peak_ratio 控制，默认 onset 占 20%、peak 占 40%、recovery 占 40%。
    """
    ONSET = "onset"         # 发病期：强度从 0 线性上升到 1
    PEAK = "peak"           # 高峰期：强度保持 1.0
    RECOVERY = "recovery"   # 恢复期：强度从 1 线性下降到 0


@dataclass
class BaseEvent:
    """
    事件基类。

    每个事件实例代表一次疾病/受伤发作，具有以下属性：
      - name              : 事件名称（如 "fever"、"injury"）
      - base_duration_days: 基础持续天数（未经 Trait 修正前）
      - duration_days     : 实际持续天数（已经过 Trait severity multiplier 修正）
      - severity          : 严重度倍率（1.0 为正常，>1.0 更严重）
      - day_index         : 当前是事件的第几天（从 0 开始）

    子类需覆盖：
      - name, base_duration_days
      - vital_effect()         → 返回瞬时值叠加量
      - steps_multiplier_value() → 返回步数倍率
      - gps_sigma_multiplier()   → 返回 GPS σ 倍率（可选，基类有默认实现）
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
        """根据当前进度 (day_index / duration_days) 判断所处阶段"""
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
        - onset:    线性上升  0 → 1（病情逐渐加重）
        - peak:     保持 1.0（病情最严重）
        - recovery: 线性下降  1 → 0（逐渐康复）

        intensity 会被 vital_effect() 和 steps_multiplier_value() 使用，
        用来按阶段调整事件对生理指标和步数的影响程度。
        """
        progress = self.day_index / max(self.duration_days, 1)
        phase = self.phase
        if phase == EventPhase.ONSET:
            # onset 阶段：从 0 线性上升到 1
            return progress / max(self.onset_ratio, 1e-9)
        elif phase == EventPhase.PEAK:
            # peak 阶段：保持最大强度
            return 1.0
        else:
            # recovery 阶段：从 1 线性下降到 0
            rec_start = self.onset_ratio + self.peak_ratio
            rec_len = 1.0 - rec_start
            return max(0.0, 1.0 - (progress - rec_start) / max(rec_len, 1e-9))

    @property
    def is_finished(self) -> bool:
        """判断事件是否已结束（day_index >= duration_days）"""
        return self.day_index >= self.duration_days

    def advance_day(self) -> None:
        """推进一天（由 EventManager 在每日午夜调用）"""
        self.day_index += 1

    def vital_effect(self) -> dict:
        """
        返回对瞬时值的叠加 {heart_rate: +x, resp_rate: +y, temperature: +z}。

        基类返回空 dict（无影响），子类覆盖此方法实现具体效果。
        叠加量通常与 intensity * severity 成正比。
        """
        return {}

    def steps_multiplier_value(self) -> float:
        """
        返回 Δsteps 的乘法倍率（<1 表示步数减少）。

        默认逻辑：
          - onset:    0.8（步数略减）
          - peak:     0.3（步数大幅减少）
          - recovery: 0.6 → 1.0（逐渐恢复到正常步数）
        """
        phase = self.phase
        if phase == EventPhase.ONSET:
            return 0.8
        elif phase == EventPhase.PEAK:
            return 0.3
        else:
            # recovery 阶段：根据恢复进度从 0.6 线性恢复到 1.0
            recovery_progress = 0.0
            rec_start = self.onset_ratio + self.peak_ratio
            rec_len = 1.0 - rec_start
            progress = self.day_index / max(self.duration_days, 1)
            if rec_len > 0:
                recovery_progress = (progress - rec_start) / rec_len
            return 0.6 + 0.4 * recovery_progress

    def gps_sigma_multiplier(self) -> float:
        """
        返回 GPS σ 的乘法倍率（<1 表示活动范围缩小）。

        默认逻辑：max(0.1, 1.0 - intensity * 0.5)，
        即在 peak 时活动范围缩小到正常的 50%，最低不低于 10%。
        """
        return max(0.1, 1.0 - self.intensity * 0.5)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(day={self.day_index}/{self.duration_days}, "
            f"phase={self.phase.value}, intensity={self.intensity:.2f})"
        )
