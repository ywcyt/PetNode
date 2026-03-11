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

    效果概述：
    - 呼吸频率均值 +4 次/分钟，RR 波动 ×1.2（呼吸更不稳定）
    - 感冒事件触发概率提高（cold ×1.5）
    - 感冒事件持续时间 +20%，严重度 ×1.2
    - 行为倾向：更多 sleeping/resting，更少 running（呼吸道不好，不爱剧烈运动）
    - 慢性波动：RR drift 幅度 2，每 60 ticks 更新一次
      （即使没有活跃事件，夜间也可能出现呼吸频率偏高的情况）
    """

    name = "RespiratoryRisk"

    # 基线偏移：呼吸频率均值 +4 次/分钟，RR 波动更大 (×1.2)
    baseline = BaselineModifiers(
        resp_rate_mean_offset=4.0,
        rr_variability_multiplier=1.2,
    )
    # 事件触发概率倍率：更容易感冒
    event_hazard = EventHazardMultipliers(
        cold=1.5,
    )
    # 事件严重度倍率：感冒时症状更严重、病程更长
    event_severity = EventSeverityMultipliers(
        cold_severity=1.2,
        cold_duration=1.2,
    )
    # 行为概率修正：更多睡觉/休息，更少跑步
    behavior = BehaviorModifiers(
        sleeping_add=0.02,
        resting_add=0.02,
        running_add=-0.03,
    )
    # GPS 位移不做额外修正
    gps_sigma = GpsSigmaMultipliers()
    # 步数不做额外修正
    steps_multiplier = 1.0

    # 慢性波动配置：呼吸频率漂移幅度 2
    drift_hr_amplitude = 0.0
    drift_rr_amplitude = 2.0
    drift_update_ticks = 60
