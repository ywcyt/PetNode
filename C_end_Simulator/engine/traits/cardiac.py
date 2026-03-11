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

    效果概述：
    - 静息心率均值 +10 bpm，HR 波动 ×1.2（心率更不稳定）
    - 发烧/中暑事件触发概率提高（fever ×1.2, heatstroke ×1.1）
    - 发烧事件持续时间 +30%，严重度 ×1.3（病程更长、症状更重）
    - 行为倾向：更多 sleeping/resting，更少 running（心脏负担大，不爱剧烈运动）
    - 慢性波动：HR drift 幅度 3 bpm，每 60 ticks 更新一次
      （即使没有活跃事件，也会出现持续数小时的心率偏高/偏低）
    """

    name = "CardiacRisk"

    # 基线偏移：心率均值 +10 bpm，心率波动更大 (×1.2)
    baseline = BaselineModifiers(
        heart_rate_mean_offset=10.0,
        hr_variability_multiplier=1.2,
    )
    # 事件触发概率倍率：更容易发烧和中暑
    event_hazard = EventHazardMultipliers(
        fever=1.2,
        heatstroke=1.1,
    )
    # 事件严重度倍率：发烧时症状更严重、病程更长
    event_severity = EventSeverityMultipliers(
        fever_severity=1.3,
        fever_duration=1.3,
    )
    # 行为概率修正：更多睡觉/休息，更少跑步
    behavior = BehaviorModifiers(
        sleeping_add=0.03,
        resting_add=0.02,
        running_add=-0.04,
    )
    # GPS 位移不做额外修正
    gps_sigma = GpsSigmaMultipliers()
    # 步数不做额外修正
    steps_multiplier = 1.0

    # 慢性波动配置：心率漂移幅度 3 bpm
    drift_hr_amplitude = 3.0
    drift_rr_amplitude = 0.0
    drift_update_ticks = 60
