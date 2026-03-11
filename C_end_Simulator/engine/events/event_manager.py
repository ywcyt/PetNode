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

# 每类事件的基础日触发概率
_BASE_HAZARDS: dict[str, float] = {
    "fever": 0.02,
    "injury": 0.01,
}

# 事件类型 → 构造函数
_EVENT_FACTORIES: dict[str, type] = {
    "fever": FeverEvent,
    "injury": InjuryEvent,
}


@dataclass
class EventManager:
    """管理当前活跃事件（同时最多 1 个）"""

    active_event: Optional[BaseEvent] = None
    _rng: np.random.Generator = field(
        default_factory=lambda: np.random.default_rng()
    )

    def set_rng(self, rng: np.random.Generator) -> None:
        self._rng = rng

    def advance_day(self, traits: list[BaseTrait]) -> None:
        """每天午夜调用一次"""
        if self.active_event is not None:
            self.active_event.advance_day()
            if self.active_event.is_finished:
                self.active_event = None
            return

        # 没有活跃事件 → 尝试触发
        hazards: dict[str, float] = {}
        for event_name, base_h in _BASE_HAZARDS.items():
            h = base_h
            for trait in traits:
                h *= getattr(trait.event_hazard, event_name, 1.0)
            hazards[event_name] = h

        # 按独立 Bernoulli 抽样，最多触发 1 个
        triggered: list[str] = []
        for event_name, h in hazards.items():
            if self._rng.random() < h:
                triggered.append(event_name)

        if not triggered:
            return

        # 若多个同时触发，随机选一个
        chosen = self._rng.choice(triggered)
        self._trigger_event(chosen, traits)

    def _trigger_event(self, event_name: str, traits: list[BaseTrait]) -> None:
        cls = _EVENT_FACTORIES[event_name]
        event = cls()
        event.duration_days = event.base_duration_days

        # 应用 trait 对持续时间和严重度的影响
        for trait in traits:
            dur_key = f"{event_name}_duration"
            sev_key = f"{event_name}_severity"
            event.duration_days = int(
                event.duration_days
                * getattr(trait.event_severity, dur_key, 1.0)
            )
            event.severity *= getattr(trait.event_severity, sev_key, 1.0)

        event.duration_days = max(event.duration_days, 1)
        self.active_event = event
