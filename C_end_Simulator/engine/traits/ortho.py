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

    效果概述：
    - 受伤事件触发概率翻倍（injury ×2.0），更容易拉伤/跛行
    - 受伤事件持续时间翻倍（injury duration ×2.0），康复更慢
    - 行为倾向：显著降低 running 概率 (-6%)，略降低 walking 概率 (-2%)
    - GPS 活动范围缩小：walking σ ×0.7，running σ ×0.6（移动更少）
    - 步数减少 25%（steps_multiplier = 0.75）
    - 无慢性波动（不直接影响心率/呼吸频率的基线，但通过减少活动量间接体现）
    """

    name = "OrthoRisk"

    # 基线偏移：无（骨骼问题不直接影响心率/呼吸/体温的基线）
    baseline = BaselineModifiers()
    # 事件触发概率倍率：受伤概率翻倍
    event_hazard = EventHazardMultipliers(
        injury=2.0,
    )
    # 事件严重度倍率：受伤时严重度 ×1.2，持续时间翻倍
    event_severity = EventSeverityMultipliers(
        injury_severity=1.2,
        injury_duration=2.0,
    )
    # 行为概率修正：显著减少跑步 (-6%)，略减少走路 (-2%)，稍增加睡觉/休息
    behavior = BehaviorModifiers(
        sleeping_add=0.01,
        resting_add=0.02,
        walking_add=-0.02,
        running_add=-0.06,
    )
    # GPS 位移修正：散步/跑步时活动范围缩小
    gps_sigma = GpsSigmaMultipliers(
        walking=0.7,
        running=0.6,
    )
    # 步数倍率：活动量减少 25%
    steps_multiplier = 0.75

    # 无慢性波动（骨骼问题通过行为层和步数层体现，不通过 drift）
    drift_hr_amplitude = 0.0
    drift_rr_amplitude = 0.0
    drift_update_ticks = 60
