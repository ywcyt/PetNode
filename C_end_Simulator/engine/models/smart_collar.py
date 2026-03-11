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

# 四种行为状态：sleeping（睡觉）、resting（休息）、walking（散步）、running（奔跑）
BEHAVIORS = ["sleeping", "resting", "walking", "running"]

# 行为基准转移矩阵 P0 —— 行=当前状态, 列=下一状态
# 顺序: sleeping, resting, walking, running
# 不同时段（night/morning/daytime/evening）对应不同的转移概率，
# 例如 night 时 sleeping→sleeping 的概率 (0.80) 远大于 daytime (0.25)
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
# 每种行为状态对应不同的生理指标正态分布参数：
#   - sleeping: 心率低 (60±5)、呼吸慢 (14±2)、体温较低 (38.2±0.1)
#   - running:  心率高 (140±15)、呼吸快 (40±6)、体温较高 (39.2±0.25)
_VITAL_BASE: dict[str, dict[str, tuple[float, float]]] = {
    "sleeping": {"heart_rate": (60, 5),  "resp_rate": (14, 2), "temperature": (38.2, 0.1)},
    "resting":  {"heart_rate": (75, 8),  "resp_rate": (18, 3), "temperature": (38.4, 0.15)},
    "walking":  {"heart_rate": (100, 10), "resp_rate": (25, 4), "temperature": (38.7, 0.2)},
    "running":  {"heart_rate": (140, 15), "resp_rate": (40, 6), "temperature": (39.2, 0.25)},
}

# 行为 → Δsteps 基准 (mean, std)
# 每个 tick 产生的步数增量：sleeping 不产生步数，running 每 tick 约 200 步
_STEPS_BASE: dict[str, tuple[float, float]] = {
    "sleeping": (0, 0),
    "resting":  (0, 1),
    "walking":  (80, 15),
    "running":  (200, 30),
}

# 行为 → GPS σ (度)
# 每个 tick 的 GPS 位移标准差：sleeping 完全不动，running 位移最大
_GPS_SIGMA: dict[str, float] = {
    "sleeping": 0.0,
    "resting":  0.000005,
    "walking":  0.00005,
    "running":  0.0002,
}


# ────────────────── 工具函数 ──────────────────

def _time_period(hour: int) -> str:
    """
    根据小时数判断时间段。

    时间段划分规则：
      - night:   22:00 ~ 06:00（夜间，sleeping 概率最高）
      - morning: 06:00 ~ 09:00（早晨，活动概率逐渐上升）
      - daytime: 09:00 ~ 18:00（白天，walking/running 概率最高）
      - evening: 18:00 ~ 22:00（傍晚，活动概率逐渐下降）
    """
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
        tick_interval: timedelta = timedelta(minutes=1),
        seed: Optional[int] = None,
    ) -> None:
        # 初始化 NumPy 随机数生成器（可通过 seed 控制可复现性）
        self._rng = np.random.default_rng(seed)
        # 如果未传入 profile，则使用 RNG 随机生成一个（确保同 seed 可复现）
        self.profile = profile or DogProfile.random_profile(rng=self._rng)
        self.tick_interval = tick_interval

        # 时钟：模拟时间从 start_time 开始，每次 generate_one_record() 前进 tick_interval
        self.sim_time = start_time or datetime(2025, 6, 1, 0, 0, 0)
        self._current_day = self.sim_time.date()

        # 行为状态：初始为 sleeping（凌晨开始）
        self._behavior: str = "sleeping"

        # 日累计步数：一天内只增不减，跨天清零
        self._today_steps: int = 0

        # GPS 坐标：初始化为狗的家庭基准位置
        self._gps_lat: float = self.profile.home_lat
        self._gps_lng: float = self.profile.home_lng

        # 事件管理器：管理疾病/受伤等长期事件，共享同一个 RNG 以保证可复现
        self._event_mgr = EventManager()
        self._event_mgr.set_rng(self._rng)

        # 初始化 trait drift（慢性波动初始值）
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
        # 1) sim_time += tick_interval   —— 推进模拟时钟
        self.sim_time += self.tick_interval

        # 2) 跨天检查：如果日期变了，清零日累计步数并推进事件管理器
        new_day = self.sim_time.date()
        if new_day != self._current_day:
            self._current_day = new_day
            self._today_steps = 0
            # EventManager.advance_day() 会推进当前事件或尝试触发新事件
            self._event_mgr.advance_day(self.profile.traits)

        # 3) 根据当前小时判断时间段（night/morning/daytime/evening）
        period = _time_period(self.sim_time.hour)

        # 4) 行为状态转移：基于 P0 矩阵 + Trait 修正 + Event 修正
        self._behavior = self._next_behavior(period)

        # 5) 根据当前行为状态生成瞬时值基准（正态分布采样）
        vital = self._base_vitals(self._behavior)

        # 6) 叠加 Trait 基线偏移（永久性）和 Trait drift（慢性波动）
        vital["heart_rate"] += self.profile.hr_mean_offset
        vital["resp_rate"] += self.profile.rr_mean_offset
        vital["temperature"] += self.profile.temp_mean_offset

        # 遍历每个 trait，更新 drift 计数器并叠加当前漂移值
        for trait in self.profile.traits:
            trait.update_drift(self._rng)
            vital["heart_rate"] += trait.drift_hr
            vital["resp_rate"] += trait.drift_rr

        # 7) 计算本 tick 新增步数 Δsteps（受行为状态、Trait、Event 影响）
        delta_steps = self._delta_steps(self._behavior)

        # 8) 累加到日步数（确保非负）
        self._today_steps += max(0, int(delta_steps))

        # 9) 更新 GPS 坐标（位移幅度由行为状态决定，受 Trait/Event 修正）
        self._update_gps(self._behavior)

        # 10) 叠加 Event 对瞬时值的影响（发烧→体温升高、心率加快等）
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

        # 11) 将瞬时值 clamp 到合理范围，防止异常值
        #     心率: 30~250 bpm, 呼吸频率: 8~80 次/分, 体温: 36.0~42.0 °C
        vital["heart_rate"] = max(30, min(250, round(vital["heart_rate"], 1)))
        vital["resp_rate"] = max(8, min(80, round(vital["resp_rate"], 1)))
        vital["temperature"] = max(36.0, min(42.0, round(vital["temperature"], 2)))

        # 组装最终输出记录（共 12 个字段）
        return {
            "device_id": self.profile.dog_id,          # 设备（狗）唯一标识
            "timestamp": self.sim_time.isoformat(),    # 模拟时间戳 (ISO 8601)
            "behavior": self._behavior,                # 当前行为状态
            "heart_rate": vital["heart_rate"],          # 心率 (bpm)
            "resp_rate": vital["resp_rate"],            # 呼吸频率 (次/分钟)
            "temperature": vital["temperature"],        # 体温 (°C)
            "steps": self._today_steps,                # 今日累计步数
            "battery": 100,                            # 电量（当前阶段不模拟，固定 100）
            "gps_lat": round(self._gps_lat, 6),        # GPS 纬度
            "gps_lng": round(self._gps_lng, 6),        # GPS 经度
            "event": event_name,                       # 当前活跃事件名称（无事件时为 None）
            "event_phase": event_phase,                # 事件阶段（onset/peak/recovery，无事件时为 None）
        }

    # ──────────── 内部方法 ────────────

    def _next_behavior(self, period: str) -> str:
        """
        行为状态转移：P0 → Trait 修正 → Event 修正 → choice

        流程：
        1. 取当前时段的基础转移概率行 P0[period][current_behavior]
        2. 叠加所有 Trait 的行为修正（加法修正，如 CardiacRisk 增加 sleeping 概率）
        3. 叠加活跃事件的影响（peak 时强力增加 sleeping/resting 概率）
        4. 归一化后用 RNG 按概率抽样选择下一个行为
        """
        # 复制一份基础转移概率（避免修改原始矩阵）
        p0 = list(_P0[period][self._behavior])

        # Trait 修正：每个 trait 的 BehaviorModifiers 以加法叠加
        for trait in self.profile.traits:
            bm = trait.behavior
            p0[0] += bm.sleeping_add
            p0[1] += bm.resting_add
            p0[2] += bm.walking_add
            p0[3] += bm.running_add

        # Event 修正：peak 阶段强力提高 sleeping/resting，降低 walking/running
        active = self._event_mgr.active_event
        if active is not None:
            intensity = active.intensity
            p0[0] += 0.15 * intensity      # sleeping 概率增加
            p0[1] += 0.10 * intensity      # resting 概率增加
            p0[2] -= 0.10 * intensity      # walking 概率减少
            p0[3] -= 0.15 * intensity      # running 概率减少

        # 归一化确保概率和为 1（负值截 0）
        probs = _normalize(p0)
        return str(self._rng.choice(BEHAVIORS, p=probs))

    def _base_vitals(self, behavior: str) -> dict:
        """
        根据行为生成瞬时值基准（正态分布）。

        每个指标从 _VITAL_BASE 中取对应行为的 (mean, std)，
        然后应用 Trait 的 variability multiplier 调整标准差（心脏问题→HR 波动更大）。
        最终用 RNG 正态采样生成瞬时值。
        """
        specs = _VITAL_BASE[behavior]
        result = {}
        for key, (mean, std) in specs.items():
            # 应用 trait variability multiplier（例如 CardiacRisk 使 HR 的 std ×1.2）
            actual_std = std
            if key == "heart_rate":
                actual_std *= self.profile.hr_var_mult
            elif key == "resp_rate":
                actual_std *= self.profile.rr_var_mult
            result[key] = float(self._rng.normal(mean, actual_std))
        return result

    def _delta_steps(self, behavior: str) -> float:
        """
        计算本 tick 新增步数（Δsteps）。

        流程：
        1. 从 _STEPS_BASE 取行为对应的正态分布参数
        2. 若 sleeping（mean=0, std=0），直接返回 0
        3. 正态采样后依次应用 Trait 步数倍率和 Event 步数倍率
        4. 确保返回值非负
        """
        mean, std = _STEPS_BASE[behavior]
        if mean == 0 and std == 0:
            return 0.0

        delta = float(self._rng.normal(mean, std))

        # Trait 修正：例如 OrthoRisk 的 steps_multiplier = 0.75（少走 25%）
        delta *= self.profile.steps_mult

        # Event 修正：例如发烧 peak 阶段步数乘以约 0.3
        active = self._event_mgr.active_event
        if active is not None:
            delta *= active.steps_multiplier_value()

        return max(0.0, delta)

    def _update_gps(self, behavior: str) -> None:
        """
        更新 GPS 坐标。

        每 tick 的位移量 = N(0, σ)，σ 取决于行为状态：
          - sleeping: σ=0（完全不动）
          - resting:  σ≈0（微小抖动）
          - walking:  σ=小（正常活动范围）
          - running:  σ=大（大范围移动）

        Trait 修正：OrthoRisk 降低 walking/running 的 σ（活动范围缩小）
        Event 修正：受伤 peak 阶段 σ≈0（基本不动）
        """
        sigma = _GPS_SIGMA[behavior]
        if sigma <= 0:
            return

        # Trait 修正：通过 GpsSigmaMultipliers 调整活动范围
        for trait in self.profile.traits:
            if behavior == "walking":
                sigma *= trait.gps_sigma.walking
            elif behavior == "running":
                sigma *= trait.gps_sigma.running

        # Event 修正：疾病/受伤时活动范围缩小
        active = self._event_mgr.active_event
        if active is not None:
            sigma *= active.gps_sigma_multiplier()

        # 对纬度和经度分别做正态偏移
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

