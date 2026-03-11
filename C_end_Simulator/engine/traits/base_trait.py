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
    """
    对瞬时值基准的永久偏移。

    这些偏移在整个模拟过程中固定不变，叠加到每次生成的瞬时值上：
      - heart_rate_mean_offset : 心率均值偏移 (bpm)，正值表示基线心率更高
      - resp_rate_mean_offset  : 呼吸频率均值偏移 (次/分钟)
      - temperature_mean_offset: 体温均值偏移 (°C)
      - hr_variability_multiplier : 心率标准差倍率（>1 表示心率波动更大）
      - rr_variability_multiplier : 呼吸频率标准差倍率
    """
    heart_rate_mean_offset: float = 0.0
    resp_rate_mean_offset: float = 0.0
    temperature_mean_offset: float = 0.0
    hr_variability_multiplier: float = 1.0
    rr_variability_multiplier: float = 1.0


@dataclass
class EventHazardMultipliers:
    """
    对事件触发概率的倍率。

    每类事件有一个基础日触发概率（base_hazard），Trait 的 hazard_multiplier 会乘以该概率：
      - fever     : 发烧事件触发概率倍率
      - cold      : 感冒事件触发概率倍率（当前未实现该事件，留作扩展）
      - heatstroke: 中暑事件触发概率倍率（当前未实现该事件，留作扩展）
      - injury    : 受伤事件触发概率倍率
    例如 OrthoRisk 的 injury=2.0 表示骨骼问题倾向的狗受伤概率翻倍。
    """
    fever: float = 1.0
    cold: float = 1.0
    heatstroke: float = 1.0
    injury: float = 1.0


@dataclass
class EventSeverityMultipliers:
    """
    对事件严重度和持续时间的倍率。

    每类事件有两个修正维度：
      - severity（严重度）: 影响瞬时值叠加量的强度（>1 表示症状更严重）
      - duration（持续时间）: 影响事件总天数（>1 表示病程更长）
    例如 CardiacRisk 的 fever_severity=1.3 表示心脏问题倾向的狗发烧时症状更严重。
    """
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
    """
    对行为转移概率的修正（加法，修正后会重新归一化）。

    直接叠加到 P0 转移矩阵的概率值上，正值增加该行为概率，负值降低：
      - sleeping_add: 睡觉概率修正（正值→更容易入睡）
      - resting_add : 休息概率修正
      - walking_add : 散步概率修正（负值→更少走路）
      - running_add : 奔跑概率修正（负值→更少跑动）
    修正后会经过 _normalize() 确保概率和为 1。
    """
    sleeping_add: float = 0.0
    resting_add: float = 0.0
    walking_add: float = 0.0
    running_add: float = 0.0


@dataclass
class GpsSigmaMultipliers:
    """
    对 GPS 偏移标准差的修正。

    乘以行为对应的 GPS σ 值，<1 表示活动范围缩小：
      - walking: 散步时的 GPS 位移倍率
      - running: 奔跑时的 GPS 位移倍率
    例如 OrthoRisk 的 walking=0.7 表示骨骼问题倾向的狗散步时移动范围减少 30%。
    """
    walking: float = 1.0
    running: float = 1.0


class BaseTrait:
    """
    Trait 基类，子类只需覆盖类属性即可定义一种新的慢性体质特质。

    Trait 系统的核心设计：
    1. 每个 Trait 通过 5 组修正参数影响模拟的各个维度
    2. drift 机制实现慢性波动——即使没有活跃事件，也会在心率/呼吸频率上产生持续数小时的小幅偏移
    3. drift 不是每 tick 重新采样，而是每 drift_update_ticks 更新一次（默认 60 ticks = 1 小时）
    """

    name: str = "base"

    # 5 组修正参数——子类覆盖这些类属性即可
    baseline: BaselineModifiers = BaselineModifiers()           # 基线偏移
    event_hazard: EventHazardMultipliers = EventHazardMultipliers()  # 事件触发概率倍率
    event_severity: EventSeverityMultipliers = EventSeverityMultipliers()  # 事件严重度倍率
    behavior: BehaviorModifiers = BehaviorModifiers()           # 行为转移概率修正
    gps_sigma: GpsSigmaMultipliers = GpsSigmaMultipliers()      # GPS 位移修正
    steps_multiplier: float = 1.0                               # 步数倍率（<1 表示活动量减少）

    # drift 配置：用于模拟慢性病的短周期波动
    drift_hr_amplitude: float = 0.0    # 心率漂移幅度（0 表示不漂移）
    drift_rr_amplitude: float = 0.0    # 呼吸频率漂移幅度
    drift_update_ticks: int = 60       # 每隔多少 tick 更新一次 drift（60 tick ≈ 1 小时）

    def __init__(self) -> None:
        # drift 当前值——在 update_drift() 中按周期更新
        self._drift_hr: float = 0.0
        self._drift_rr: float = 0.0
        # tick 计数器，达到 drift_update_ticks 时触发更新
        self._tick_counter: int = 0

    def update_drift(self, rng: np.random.Generator) -> None:
        """
        每 drift_update_ticks 更新一次慢性波动值。

        漂移值从 N(0, amplitude) 正态分布中采样，
        模拟慢性病患者在数小时内持续偏高/偏低的生理指标。
        """
        self._tick_counter += 1
        if self._tick_counter >= self.drift_update_ticks:
            self._tick_counter = 0
            if self.drift_hr_amplitude > 0:
                self._drift_hr = rng.normal(0, self.drift_hr_amplitude)
            if self.drift_rr_amplitude > 0:
                self._drift_rr = rng.normal(0, self.drift_rr_amplitude)

    @property
    def drift_hr(self) -> float:
        """当前心率漂移值 (bpm)"""
        return self._drift_hr

    @property
    def drift_rr(self) -> float:
        """当前呼吸频率漂移值 (次/分钟)"""
        return self._drift_rr

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
