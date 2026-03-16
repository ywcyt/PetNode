"""
BaseTrait —— Trait 层抽象基类
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass

# =====================================================================
# 这里的 @dataclass 必须在 BaseTrait 之前定义，否则 IDE 找不到它们
# =====================================================================

@dataclass
class BaselineModifiers:
    heart_rate_mean_offset: float = 0.0
    resp_rate_mean_offset: float = 0.0
    temperature_mean_offset: float = 0.0
    hr_variability_multiplier: float = 1.0
    rr_variability_multiplier: float = 1.0


@dataclass
class EventHazardMultipliers:
    fever: float = 1.0
    cold: float = 1.0
    heatstroke: float = 1.0
    injury: float = 1.0


@dataclass
class EventSeverityMultipliers:
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
    sleeping_add: float = 0.0
    resting_add: float = 0.0
    walking_add: float = 0.0
    running_add: float = 0.0


@dataclass
class GpsSigmaMultipliers:
    walking: float = 1.0
    running: float = 1.0


# =====================================================================
# 核心架构：带有自动注册表和钩子的基类
# =====================================================================

class BaseTrait:
    """
    Trait 基类，子类只需覆盖类属性即可定义一种新的慢性体质特质。
    """
    name: str = "base"

    # ==================== 新增：全自动注册中心 ====================
    _registry: dict[str, type['BaseTrait']] = {}

    def __init_subclass__(cls, **kwargs):
        """钩子：当 CardiacRisk 等子类继承本类时，自动触发注册"""
        super().__init_subclass__(**kwargs)
        if cls is BaseTrait:
            return

        if hasattr(cls, 'name') and cls.name and cls.name != "base":
            if cls.name in cls._registry:
                import warnings
                warnings.warn(f"Trait 名称 '{cls.name}' 已被注册，发生冲突！")
            else:
                cls._registry[cls.name] = cls  # 隐式压入注册表

    @classmethod
    def get_trait(cls, name: str) -> type['BaseTrait'] | None:
        """全局接口：根据名字获取体质类"""
        return cls._registry.get(name)

    @classmethod
    def get_all_trait_names(cls) -> list[str]:
        """全局接口：获取当前系统加载的所有体质名称"""
        return list(cls._registry.keys())
    # ==============================================================

    # 5 组修正参数——现在 IDE 肯定能找到它们了
    baseline: BaselineModifiers = BaselineModifiers()
    event_hazard: EventHazardMultipliers = EventHazardMultipliers()
    event_severity: EventSeverityMultipliers = EventSeverityMultipliers()
    behavior: BehaviorModifiers = BehaviorModifiers()
    gps_sigma: GpsSigmaMultipliers = GpsSigmaMultipliers()
    steps_multiplier: float = 1.0

    # drift 配置
    drift_hr_amplitude: float = 0.0
    drift_rr_amplitude: float = 0.0
    drift_update_ticks: int = 60

    def __init__(self) -> None:
        self._drift_hr: float = 0.0
        self._drift_rr: float = 0.0
        self._tick_counter: int = 0

    def update_drift(self, rng: np.random.Generator) -> None:
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