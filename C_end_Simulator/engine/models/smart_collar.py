"""
SmartCollar —— 智能项圈类 (OOP 封装，产生模拟数据)

核心职责：
  每次调用 generate_one_record() 产出一条 dict 记录。
  内部维护: SimClock、行为状态机、日累计值、GPS、EventManager、Trait drift。

检测维度参考（凃维康调研）:
  1. 运动量、卡路里消耗、静息时间
  2. 睡眠指标（碎片化睡眠）
  3. 异常行为检测
  4. 呼吸频率、异常喘息、咳嗽
  5. 吠叫频率
  6. 静息心率
  7. 体温变化趋势
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from engine.models.dog_profile import DogProfile
from engine.events.event_manager import EventManager

# ────────────────── 常量 ──────────────────

BEHAVIORS = ["sleeping", "resting", "walking", "running"]

# 行为基准转移矩阵 P0 —— 行=当前状态, 列=下一状态
# 顺序: sleeping, resting, walking, running
_P0: dict[str, dict[str, list[float]]] = {
    "night": {
        "sleeping": [0.80, 0.15, 0.04, 0.01],
        "resting":  [0.40, 0.45, 0.12, 0.03],
        "walking":  [0.20, 0.35, 0.35, 0.10],
        "running":  [0.15, 0.30, 0.35, 0.20],
    },
    "morning": {
        "sleeping": [0.30, 0.30, 0.30, 0.10],
        "resting":  [0.15, 0.35, 0.35, 0.15],
        "walking":  [0.05, 0.20, 0.45, 0.30],
        "running":  [0.05, 0.15, 0.40, 0.40],
    },
    "daytime": {
        "sleeping": [0.25, 0.35, 0.30, 0.10],
        "resting":  [0.10, 0.35, 0.35, 0.20],
        "walking":  [0.05, 0.15, 0.50, 0.30],
        "running":  [0.05, 0.10, 0.40, 0.45],
    },
    "evening": {
        "sleeping": [0.50, 0.30, 0.15, 0.05],
        "resting":  [0.25, 0.40, 0.25, 0.10],
        "walking":  [0.15, 0.30, 0.40, 0.15],
        "running":  [0.10, 0.25, 0.40, 0.25],
    },
}

# 行为 → 瞬时值基准 (mean, std)
_VITAL_BASE: dict[str, dict[str, tuple[float, float]]] = {
    "sleeping": {"heart_rate": (60, 5),  "resp_rate": (14, 2), "temperature": (38.2, 0.1)},
    "resting":  {"heart_rate": (75, 8),  "resp_rate": (18, 3), "temperature": (38.4, 0.15)},
    "walking":  {"heart_rate": (100, 10), "resp_rate": (25, 4), "temperature": (38.7, 0.2)},
    "running":  {"heart_rate": (140, 15), "resp_rate": (40, 6), "temperature": (39.2, 0.25)},
}

# 行为 → Δsteps 基准 (mean, std)
_STEPS_BASE: dict[str, tuple[float, float]] = {
    "sleeping": (0, 0),
    "resting":  (0, 1),
    "walking":  (80, 15),
    "running":  (200, 30),
}

# 行为 → GPS σ (度)
_GPS_SIGMA: dict[str, float] = {
    "sleeping": 0.0,
    "resting":  0.000005,
    "walking":  0.00005,
    "running":  0.0002,
}


# ────────────────── 工具函数 ──────────────────

def _time_period(hour: int) -> str:
    if 22 <= hour or hour < 6:
        return "night"
    elif 6 <= hour < 9:
        return "morning"
    elif 9 <= hour < 18:
        return "daytime"
    else:
        return "evening"


def _normalize(probs: list[float]) -> list[float]:
    """归一化概率（保证和为 1，负值截 0）"""
    arr = [max(p, 0.0) for p in probs]
    s = sum(arr)
    if s <= 0:
        n = len(arr)
        return [1.0 / n] * n
    return [p / s for p in arr]


# ────────────────── SmartCollar ──────────────────

class SmartCollar:
    """
    智能项圈模拟器

    Parameters
    ----------
    profile : DogProfile
        狗的长期属性
    start_time : datetime
        模拟起始时间
    tick_interval : timedelta
        每 tick 推进的模拟时间（默认 15 分钟）
    seed : int | None
        随机种子（可复现）
    """

    def __init__(
        self,
        profile: Optional[DogProfile] = None,
        start_time: Optional[datetime] = None,
        tick_interval: timedelta = timedelta(minutes=15),
        seed: Optional[int] = None,
    ) -> None:
        self._rng = np.random.default_rng(seed)
        self.profile = profile or DogProfile.random_profile(rng=self._rng)
        self.tick_interval = tick_interval

        # 时钟
        self.sim_time = start_time or datetime(2025, 6, 1, 0, 0, 0)
        self._current_day = self.sim_time.date()

        # 行为状态
        self._behavior: str = "sleeping"

        # 日累计
        self._today_steps: int = 0

        # GPS
        self._gps_lat: float = self.profile.home_lat
        self._gps_lng: float = self.profile.home_lng

        # 事件管理器
        self._event_mgr = EventManager()
        self._event_mgr.set_rng(self._rng)

        # 初始化 trait drift
        for trait in self.profile.traits:
            trait.update_drift(self._rng)

    # ──────────── 核心：生成一条记录 ────────────

    def generate_one_record(self) -> dict:
        """
        生成一条模拟数据记录（按 README 流水线顺序）

        Returns
        -------
        dict  包含 device_id, timestamp, behavior, heart_rate, resp_rate,
              temperature, steps, battery, gps_lat, gps_lng, event, event_phase
        """
        # 1) sim_time += tick_interval
        self.sim_time += self.tick_interval

        # 2) 跨天检查
        new_day = self.sim_time.date()
        if new_day != self._current_day:
            self._current_day = new_day
            self._today_steps = 0
            self._event_mgr.advance_day(self.profile.traits)

        # 3) 时间段
        period = _time_period(self.sim_time.hour)

        # 4) 行为状态转移
        self._behavior = self._next_behavior(period)

        # 5) 瞬时值基准
        vital = self._base_vitals(self._behavior)

        # 6) Trait 基线偏移 + Trait drift
        vital["heart_rate"] += self.profile.hr_mean_offset
        vital["resp_rate"] += self.profile.rr_mean_offset
        vital["temperature"] += self.profile.temp_mean_offset

        for trait in self.profile.traits:
            trait.update_drift(self._rng)
            vital["heart_rate"] += trait.drift_hr
            vital["resp_rate"] += trait.drift_rr

        # 7) Δsteps
        delta_steps = self._delta_steps(self._behavior)

        # 8) today_steps 累加
        self._today_steps += max(0, int(delta_steps))

        # 9) GPS 更新
        self._update_gps(self._behavior)

        # 10) Event 叠加
        event_name = None
        event_phase = None
        active = self._event_mgr.active_event
        if active is not None:
            effects = active.vital_effect()
            vital["heart_rate"] += effects.get("heart_rate", 0)
            vital["resp_rate"] += effects.get("resp_rate", 0)
            vital["temperature"] += effects.get("temperature", 0)
            event_name = active.name
            event_phase = active.phase.value

        # 11) clamp 边界
        vital["heart_rate"] = max(30, min(250, round(vital["heart_rate"], 1)))
        vital["resp_rate"] = max(8, min(80, round(vital["resp_rate"], 1)))
        vital["temperature"] = max(36.0, min(42.0, round(vital["temperature"], 2)))

        return {
            "device_id": self.profile.dog_id,
            "timestamp": self.sim_time.isoformat(),
            "behavior": self._behavior,
            "heart_rate": vital["heart_rate"],
            "resp_rate": vital["resp_rate"],
            "temperature": vital["temperature"],
            "steps": self._today_steps,
            "battery": 100,
            "gps_lat": round(self._gps_lat, 6),
            "gps_lng": round(self._gps_lng, 6),
            "event": event_name,
            "event_phase": event_phase,
        }

    # ──────────── 内部方法 ────────────

    def _next_behavior(self, period: str) -> str:
        """行为状态转移：P0 → Trait 修正 → Event 修正 → choice"""
        p0 = list(_P0[period][self._behavior])

        # Trait 修正
        for trait in self.profile.traits:
            bm = trait.behavior
            p0[0] += bm.sleeping_add
            p0[1] += bm.resting_add
            p0[2] += bm.walking_add
            p0[3] += bm.running_add

        # Event 修正：peak 阶段强力提高 sleeping/resting
        active = self._event_mgr.active_event
        if active is not None:
            intensity = active.intensity
            p0[0] += 0.15 * intensity
            p0[1] += 0.10 * intensity
            p0[2] -= 0.10 * intensity
            p0[3] -= 0.15 * intensity

        probs = _normalize(p0)
        return str(self._rng.choice(BEHAVIORS, p=probs))

    def _base_vitals(self, behavior: str) -> dict:
        """根据行为生成瞬时值基准（正态分布）"""
        specs = _VITAL_BASE[behavior]
        result = {}
        for key, (mean, std) in specs.items():
            # 应用 trait variability multiplier
            actual_std = std
            if key == "heart_rate":
                actual_std *= self.profile.hr_var_mult
            elif key == "resp_rate":
                actual_std *= self.profile.rr_var_mult
            result[key] = float(self._rng.normal(mean, actual_std))
        return result

    def _delta_steps(self, behavior: str) -> float:
        """计算本 tick 新增步数"""
        mean, std = _STEPS_BASE[behavior]
        if mean == 0 and std == 0:
            return 0.0

        delta = float(self._rng.normal(mean, std))

        # Trait 修正
        delta *= self.profile.steps_mult

        # Event 修正
        active = self._event_mgr.active_event
        if active is not None:
            delta *= active.steps_multiplier_value()

        return max(0.0, delta)

    def _update_gps(self, behavior: str) -> None:
        """更新 GPS 坐标"""
        sigma = _GPS_SIGMA[behavior]
        if sigma <= 0:
            return

        # Trait 修正
        for trait in self.profile.traits:
            if behavior == "walking":
                sigma *= trait.gps_sigma.walking
            elif behavior == "running":
                sigma *= trait.gps_sigma.running

        # Event 修正
        active = self._event_mgr.active_event
        if active is not None:
            sigma *= active.gps_sigma_multiplier()

        self._gps_lat += float(self._rng.normal(0, sigma))
        self._gps_lng += float(self._rng.normal(0, sigma))

    def __repr__(self) -> str:
        return (
            f"SmartCollar(profile={self.profile}, "
            f"time={self.sim_time.isoformat()}, behavior={self._behavior})"
        )


# ★ 快速验证入口
if __name__ == "__main__":
    collar = SmartCollar(seed=42)
    print(f"项圈: {collar}")
    print()
    for i in range(5):
        record = collar.generate_one_record()
        print(f"[Tick {i+1}] {record}")

