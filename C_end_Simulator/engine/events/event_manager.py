from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from engine.traits.base_trait import BaseTrait
from .base_event import BaseEvent

# ❌ 删掉所有的手动 import !
# ❌ 删掉 _BASE_HAZARDS 字典 !
# ❌ 删掉 _EVENT_FACTORIES 字典 !

@dataclass
class EventManager:
    active_event: Optional[BaseEvent] = None
    _rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng())
    
    # ... 其他代码不变 ...

    def advance_day(self, traits: list[BaseTrait]) -> None:
        if self.active_event is not None:
            self.active_event.advance_day()
            if self.active_event.is_finished:
                self.active_event = None
            return

        hazards: dict[str, float] = {}
        # 🌟 从自动注册表中获取所有的事件，全自动处理！
        for event_name, event_cls in BaseEvent.get_all_events().items():
            h = event_cls.base_hazard  # 从类中读取默认触发概率
            for trait in traits:
                h *= getattr(trait.event_hazard, event_name, 1.0)
            hazards[event_name] = h

        triggered: list[str] = []
        for event_name, h in hazards.items():
            if self._rng.random() < h:
                triggered.append(event_name)

        if not triggered:
            return

        chosen = self._rng.choice(triggered)
        self._trigger_event(chosen, traits)

    def _trigger_event(self, event_name: str, traits: list[BaseTrait]) -> None:
        # 🌟 直接从自动注册表中拿类出来实例化！
        cls = BaseEvent.get_all_events()[event_name]
        event = cls()
        event.duration_days = event.base_duration_days
        # ... 后面应用倍率的逻辑不变 ...