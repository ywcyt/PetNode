"""InjuryEvent —— 受伤/跛行事件"""

from .base_event import BaseEvent, EventPhase


class InjuryEvent(BaseEvent):
    """
    受伤/跛行事件：

    模拟狗的受伤过程（如拉伤、扭伤、跛行等）：
    - 基础持续 10 天（可被 OrthoRisk 修正，使持续时间 ×2.0，即骨骼问题的狗恢复更慢）
    - 心率略升（+8 bpm），体温略升（+0.5°C），呼吸略加速（+2）
    - 步数在 peak 阶段几乎为 0（严重跛行/卧床）
    - GPS 偏移在 peak 阶段几乎为 0（基本不移动）
    """

    name: str = "injury"
    base_duration_days: int = 10

    def vital_effect(self) -> dict:
        """
        受伤对瞬时值的影响。

        受伤的生理影响比发烧温和：
          - heart_rate:  +8 bpm × i（疼痛引起轻微心率加快）
          - resp_rate:   +2 次/分 × i（轻微呼吸加速）
          - temperature: +0.5°C × i（炎症引起轻微体温升高）
        """
        # i = intensity * severity
        i = self.intensity * self.severity
        return {
            "heart_rate": 8.0 * i,
            "resp_rate": 2.0 * i,
            "temperature": 0.5 * i,
        }

    def steps_multiplier_value(self) -> float:
        """
        受伤时步数大幅减少，peak 阶段几乎不走路。

        与基类不同的自定义逻辑：
          - onset:    0.4（步数减少 60%）
          - peak:     0.05 / severity（几乎为 0，严重度越高步数越少）
          - recovery: 0.3 → 1.0（从 30% 逐渐恢复到 100%）
        """
        phase = self.phase
        if phase == EventPhase.PEAK:
            # peak 阶段：步数接近 0，severity 越高越少
            return 0.05 / max(self.severity, 1.0)
        elif phase == EventPhase.ONSET:
            return 0.4
        else:
            # recovery 阶段：从 0.3 线性恢复到 1.0
            recovery_progress = 0.0
            rec_start = self.onset_ratio + self.peak_ratio
            rec_len = 1.0 - rec_start
            progress = self.day_index / max(self.duration_days, 1)
            if rec_len > 0:
                recovery_progress = (progress - rec_start) / rec_len
            return 0.3 + 0.7 * recovery_progress

    def gps_sigma_multiplier(self) -> float:
        """
        受伤时 GPS 活动范围大幅缩小。

        - peak 阶段：σ × 0.05（几乎不动，严重跛行）
        - 其他阶段：max(0.1, 1.0 - intensity × 0.7)（比基类的 0.5 更激进）
        """
        if self.phase == EventPhase.PEAK:
            return 0.05
        return max(0.1, 1.0 - self.intensity * 0.7)
