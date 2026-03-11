"""CardiacRisk —— 心脏问题倾向 Trait"""

from .base_trait import (
    BaseTrait,
    BaselineModifiers,
    EventHazardMultipliers,
    EventSeverityMultipliers,
    BehaviorModifiers,
    GpsSigmaMultipliers,
)


class CardiacRisk(BaseTrait):
    """
    心脏问题倾向：
    - 静息心率 +10 bpm，HR 波动 ×1.2
    - fever/heatstroke hazard ×1.2
    - fever 持续 +30%，severity ×1.3
    - 提高 sleeping/resting 概率，降低 running 概率
    - 慢性波动：HR drift 幅度 3 bpm
    """

    name = "CardiacRisk"

    baseline = BaselineModifiers(
        heart_rate_mean_offset=10.0,
        hr_variability_multiplier=1.2,
    )
    event_hazard = EventHazardMultipliers(
        fever=1.2,
        heatstroke=1.1,
    )
    event_severity = EventSeverityMultipliers(
        fever_severity=1.3,
        fever_duration=1.3,
    )
    behavior = BehaviorModifiers(
        sleeping_add=0.03,
        resting_add=0.02,
        running_add=-0.04,
    )
    gps_sigma = GpsSigmaMultipliers()
    steps_multiplier = 1.0

    drift_hr_amplitude = 3.0
    drift_rr_amplitude = 0.0
    drift_update_ticks = 60
