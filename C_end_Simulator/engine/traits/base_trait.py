"""
BaseTrait —— Trait 层抽象基类

每个 Trait 提供：
  - baseline_modifiers      : 对瞬时值均值/方差的永久偏移
  - event_hazard_multipliers: 对事件触发概率的倍率
  - event_severity_multipliers: 对事件严重度/持续时间的倍率
  - behavior_modifiers      : 对行为状态转移概率的修正
  - gps_sigma_multipliers   : 对 GPS 偏移量的修正
  - steps_multiplier        : 对 Δsteps 均值的修正
  - drift 机制              : 慢性波动（短周期小漂移）
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class BaselineModifiers:
    """对瞬时值基准的永久偏移"""
    heart_rate_mean_offset: float = 0.0
    resp_rate_mean_offset: float = 0.0
    temperature_mean_offset: float = 0.0
    hr_variability_multiplier: float = 1.0
    rr_variability_multiplier: float = 1.0


@dataclass
class EventHazardMultipliers:
    """对事件触发概率的倍率"""
    fever: float = 1.0
    cold: float = 1.0
    heatstroke: float = 1.0
    injury: float = 1.0


@dataclass
class EventSeverityMultipliers:
    """对事件严重度/持续时间的倍率"""
    fever_severity: float = 1.0
    fever_duration: float = 1.0
    cold_severity: float = 1.0
    cold_duration: float = 1.0
    injury_severity: float = 1.0
    injury_duration: float = 1.0
    heatstroke_severity: float = 1.0
    heatstroke_duration: float = 1.0


@dataclass
class BehaviorModifiers:
    """对行为转移概率的修正（加法，修正后会重新归一化）"""
    sleeping_add: float = 0.0
    resting_add: float = 0.0
    walking_add: float = 0.0
    running_add: float = 0.0


@dataclass
class GpsSigmaMultipliers:
    """对 GPS 偏移标准差的修正"""
    walking: float = 1.0
    running: float = 1.0


class BaseTrait:
    """Trait 基类，子类只需覆盖属性即可"""

    name: str = "base"

    baseline: BaselineModifiers = BaselineModifiers()
    event_hazard: EventHazardMultipliers = EventHazardMultipliers()
    event_severity: EventSeverityMultipliers = EventSeverityMultipliers()
    behavior: BehaviorModifiers = BehaviorModifiers()
    gps_sigma: GpsSigmaMultipliers = GpsSigmaMultipliers()
    steps_multiplier: float = 1.0

    # drift 配置
    drift_hr_amplitude: float = 0.0    # 心率漂移幅度
    drift_rr_amplitude: float = 0.0    # 呼吸频率漂移幅度
    drift_update_ticks: int = 60       # 每隔多少 tick 更新一次 drift

    def __init__(self) -> None:
        self._drift_hr: float = 0.0
        self._drift_rr: float = 0.0
        self._tick_counter: int = 0

    def update_drift(self, rng: np.random.Generator) -> None:
        """每 drift_update_ticks 更新一次慢性波动值"""
        self._tick_counter += 1
        if self._tick_counter >= self.drift_update_ticks:
            self._tick_counter = 0
            if self.drift_hr_amplitude > 0:
                self._drift_hr = rng.normal(0, self.drift_hr_amplitude)
            if self.drift_rr_amplitude > 0:
                self._drift_rr = rng.normal(0, self.drift_rr_amplitude)

    @property
    def drift_hr(self) -> float:
        return self._drift_hr

    @property
    def drift_rr(self) -> float:
        return self._drift_rr

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
