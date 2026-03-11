"""RespiratoryRisk —— 呼吸道问题倾向 Trait"""

from .base_trait import (
    BaseTrait,
    BaselineModifiers,
    EventHazardMultipliers,
    EventSeverityMultipliers,
    BehaviorModifiers,
    GpsSigmaMultipliers,
)


class RespiratoryRisk(BaseTrait):
    """
    呼吸道问题倾向：
    - 呼吸频率 +4，RR 波动 ×1.2
    - cold hazard ×1.5
    - cold 持续 +20%，severity ×1.2
    - 提高 sleeping/resting 概率，降低 running 概率
    - 慢性波动：RR drift 幅度 2
    """

    name = "RespiratoryRisk"

    baseline = BaselineModifiers(
        resp_rate_mean_offset=4.0,
        rr_variability_multiplier=1.2,
    )
    event_hazard = EventHazardMultipliers(
        cold=1.5,
    )
    event_severity = EventSeverityMultipliers(
        cold_severity=1.2,
        cold_duration=1.2,
    )
    behavior = BehaviorModifiers(
        sleeping_add=0.02,
        resting_add=0.02,
        running_add=-0.03,
    )
    gps_sigma = GpsSigmaMultipliers()
    steps_multiplier = 1.0

    drift_hr_amplitude = 0.0
    drift_rr_amplitude = 2.0
    drift_update_ticks = 60
