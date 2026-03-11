"""OrthoRisk —— 骨骼/关节问题倾向 Trait"""

from .base_trait import (
    BaseTrait,
    BaselineModifiers,
    EventHazardMultipliers,
    EventSeverityMultipliers,
    BehaviorModifiers,
    GpsSigmaMultipliers,
)


class OrthoRisk(BaseTrait):
    """
    骨骼/关节问题倾向：
    - injury hazard ×2.0
    - injury 持续 ×2.0
    - 显著降低 running 概率，略降低 walking 概率
    - GPS walking/running σ 下调
    - Δsteps 均值下降
    """

    name = "OrthoRisk"

    baseline = BaselineModifiers()
    event_hazard = EventHazardMultipliers(
        injury=2.0,
    )
    event_severity = EventSeverityMultipliers(
        injury_severity=1.2,
        injury_duration=2.0,
    )
    behavior = BehaviorModifiers(
        sleeping_add=0.01,
        resting_add=0.02,
        walking_add=-0.02,
        running_add=-0.06,
    )
    gps_sigma = GpsSigmaMultipliers(
        walking=0.7,
        running=0.6,
    )
    steps_multiplier = 0.75

    drift_hr_amplitude = 0.0
    drift_rr_amplitude = 0.0
    drift_update_ticks = 60
