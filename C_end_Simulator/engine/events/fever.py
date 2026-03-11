"""FeverEvent —— 发烧事件"""

from .base_event import BaseEvent


class FeverEvent(BaseEvent):
    """
    发烧事件：

    模拟狗的发烧过程：
    - 基础持续 7 天（可被 Trait 修正，如 CardiacRisk 使持续时间 ×1.3）
    - 体温升高（最高 +1.5°C），心率加快（最高 +15 bpm），呼吸加速（最高 +6 次/分钟）
    - 所有叠加量与 intensity × severity 成正比（peak 阶段最严重）
    - 步数显著减少：在基类的倍率基础上再乘以 max(0.2, 1.0 - 0.3×severity)
    """

    name: str = "fever"
    base_duration_days: int = 7

    def vital_effect(self) -> dict:
        """
        发烧对瞬时值的影响。

        叠加量 = 基准值 × intensity × severity:
          - heart_rate:  +15 bpm × i（心率加快，高烧时更明显）
          - resp_rate:   +6 次/分 × i（呼吸加速，高烧时喘息加重）
          - temperature: +1.5°C × i（体温升高，peak 时最高）
        """
        # i = intensity * severity，综合反映当前事件的影响强度
        i = self.intensity * self.severity
        return {
            "heart_rate": 15.0 * i,
            "resp_rate": 6.0 * i,
            "temperature": 1.5 * i,
        }

    def steps_multiplier_value(self) -> float:
        """
        发烧时步数进一步减少。

        在基类的阶段倍率基础上，再乘以 max(0.2, 1.0 - 0.3 × severity)，
        severity 越高步数越少，但最低不低于基类倍率的 20%。
        """
        base = super().steps_multiplier_value()
        return base * max(0.2, 1.0 - 0.3 * self.severity)
