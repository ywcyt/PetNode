# engine/events 包 —— 事件层（疾病/受伤等长期事件）
# 事件按"天"触发和推进，持续数天到数周，分为三个阶段：onset（发病期）→ peak（高峰期）→ recovery（恢复期）。
# BaseEvent 定义了事件的通用结构（阶段、强度曲线、对生理指标/步数/GPS 的影响）；
# FeverEvent（发烧）和 InjuryEvent（受伤）是两种具体事件实现；
# EventManager 负责按天推进事件生命周期，并在无活跃事件时按概率触发新事件。

from .base_event import BaseEvent, EventPhase
from .fever import FeverEvent
from .injury import InjuryEvent
from .event_manager import EventManager

__all__ = ["BaseEvent", "EventPhase", "FeverEvent", "InjuryEvent", "EventManager"]
