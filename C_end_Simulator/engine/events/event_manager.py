"""
EventManager —— 按天推进事件

职责：
  - 每天午夜（跨天时）调用 advance_day()
  - 若无 active_event：按 hazard 抽样，最多触发 1 个事件
  - 若有 active_event：推进 day_index，判断是否痊愈
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from engine.traits.base_trait import BaseTrait
from .base_event import BaseEvent
from .fever import FeverEvent
from .injury import InjuryEvent

# 每类事件的基础日触发概率（Bernoulli 分布）
# fever 每天有 2% 的基础概率触发，injury 每天有 1% 的基础概率触发
_BASE_HAZARDS: dict[str, float] = {
    "fever": 0.02,
    "injury": 0.01,
}

# 事件类型 → 构造函数映射，用于动态创建事件实例
_EVENT_FACTORIES: dict[str, type] = {
    "fever": FeverEvent,
    "injury": InjuryEvent,
}


@dataclass
class EventManager:
    """
    事件管理器——管理当前活跃事件（同时最多 1 个）。

    核心逻辑：
    1. 每天午夜（跨天时）由 SmartCollar 调用 advance_day()
    2. 若有活跃事件：推进 day_index，检查是否痊愈
    3. 若无活跃事件：计算每类事件的 hazard = base_hazard × trait_multipliers，
       按独立 Bernoulli 抽样触发（最多触发 1 个）
    4. 触发后应用 Trait 对持续时间和严重度的修正
    """

    active_event: Optional[BaseEvent] = None       # 当前活跃事件（None 表示无事件）
    _rng: np.random.Generator = field(
        default_factory=lambda: np.random.default_rng()
    )

    def set_rng(self, rng: np.random.Generator) -> None:
        """设置随机数生成器（与 SmartCollar 共享同一 RNG，确保可复现）"""
        self._rng = rng

    def advance_day(self, traits: list[BaseTrait]) -> None:
        """
        每天午夜调用一次。

        两种情况：
        1. 有活跃事件 → 推进 day_index，若已结束则清除
        2. 无活跃事件 → 计算各事件的触发概率并尝试触发新事件
        """
        if self.active_event is not None:
            # 推进现有事件
            self.active_event.advance_day()
            if self.active_event.is_finished:
                self.active_event = None    # 痊愈
            return

        # 没有活跃事件 → 尝试触发新事件
        # 计算每类事件的触发概率：base_hazard × 所有 trait 的 hazard_multiplier
        hazards: dict[str, float] = {}
        for event_name, base_h in _BASE_HAZARDS.items():
            h = base_h
            for trait in traits:
                # 通过反射获取 trait 对该事件类型的触发概率倍率
                h *= getattr(trait.event_hazard, event_name, 1.0)
            hazards[event_name] = h

        # 按独立 Bernoulli 抽样，每类事件独立判定是否触发
        triggered: list[str] = []
        for event_name, h in hazards.items():
            if self._rng.random() < h:
                triggered.append(event_name)

        if not triggered:
            return

        # 若多个同时触发（小概率），随机选一个（同时最多 1 个活跃事件）
        chosen = self._rng.choice(triggered)
        self._trigger_event(chosen, traits)

    def _trigger_event(self, event_name: str, traits: list[BaseTrait]) -> None:
        """
        创建并激活一个新事件。

        流程：
        1. 通过 _EVENT_FACTORIES 创建事件实例
        2. 遍历所有 Trait，应用 duration 和 severity 的修正倍率
        3. 确保持续时间至少为 1 天
        """
        cls = _EVENT_FACTORIES[event_name]
        event = cls()
        event.duration_days = event.base_duration_days

        # 应用 trait 对持续时间和严重度的影响
        # 例如：CardiacRisk 的 fever_duration=1.3 → 发烧持续 7×1.3≈9 天
        for trait in traits:
            dur_key = f"{event_name}_duration"
            sev_key = f"{event_name}_severity"
            event.duration_days = int(
                event.duration_days
                * getattr(trait.event_severity, dur_key, 1.0)
            )
            event.severity *= getattr(trait.event_severity, sev_key, 1.0)

        # 确保持续时间至少为 1 天
        event.duration_days = max(event.duration_days, 1)
        self.active_event = event
