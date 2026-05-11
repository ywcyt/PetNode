"""
Step 1 测试：验证数据能正确生成

测试范围（对应开发流程第一步）：
  - DogProfile    : 默认/随机 profile 生成、Trait 修正汇总、多 Trait 叠加
  - Traits        : 三种 Trait 的基线参数、drift 更新机制
  - Events        : 事件阶段推进、强度曲线、步数倍率、EventManager 触发与 Trait 影响
  - SmartCollar   : 完整的数据生成流水线——记录字段、类型、生理指标范围、
                    步数单调性与跨天清零、行为分布（昼夜差异）、GPS 移动、
                    Trait 对心率的影响、随机种子可复现性、长时间运行稳定性
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

import numpy as np
# import tests
import pytest

from engine.models.dog_profile import DogProfile
from engine.models.smart_collar import SmartCollar
from engine.traits import CardiacRisk, RespiratoryRisk, OrthoRisk
# from engine.events.base_event import BaseEvent, EventPhase
from engine.events.base_event import EventPhase
from engine.events.fever import FeverEvent
from engine.events.injury import InjuryEvent
from engine.events.event_manager import EventManager


# ────────── DogProfile 测试 ──────────

class TestDogProfile:
    """测试 DogProfile 数据类的创建和 Trait 修正汇总功能"""

    def test_default_profile(self):
        """默认 profile 应有 12 位 dog_id，medium 体型，adult 年龄，无 trait"""
        p = DogProfile()
        assert len(p.dog_id) == 12
        assert p.breed_size == "medium"
        assert p.age_stage == "adult"
        assert p.traits == []

    def test_random_profile(self):
        """随机 profile 的各字段应在合法范围内，trait 数量 0~2 个"""
        rng = np.random.default_rng(0)
        p = DogProfile.random_profile(rng)
        assert p.breed_size in ("small", "medium", "large")
        assert p.age_stage in ("puppy", "adult", "senior")
        assert 0 <= len(p.traits) <= 2

    def test_trait_modifiers(self):
        """单个 CardiacRisk trait 的修正值应正确汇总"""
        p = DogProfile(traits=[CardiacRisk()])
        assert p.hr_mean_offset == 10.0
        assert p.hr_var_mult == pytest.approx(1.2)

    def test_multiple_trait_stacking(self):
        """多个 trait 的偏移量应累加，倍率应相乘"""
        p = DogProfile(traits=[CardiacRisk(), RespiratoryRisk()])
        assert p.hr_mean_offset == 10.0  # only CardiacRisk
        assert p.rr_mean_offset == 4.0   # only RespiratoryRisk
        # variability multipliers multiply
        assert p.hr_var_mult == pytest.approx(1.2)  # CardiacRisk
        assert p.rr_var_mult == pytest.approx(1.2)  # RespiratoryRisk


# ────────── Traits 测试 ──────────

class TestTraits:
    """测试三种 Trait 的基线参数值和 drift 更新机制"""

    def test_cardiac_baseline(self):
        """CardiacRisk 应使心率均值 +10 bpm，波动 ×1.2"""
        t = CardiacRisk()
        assert t.baseline.heart_rate_mean_offset == 10.0
        assert t.baseline.hr_variability_multiplier == 1.2

    def test_respiratory_baseline(self):
        """RespiratoryRisk 应使呼吸频率均值 +4"""
        t = RespiratoryRisk()
        assert t.baseline.resp_rate_mean_offset == 4.0

    def test_ortho_steps(self):
        """OrthoRisk 应使步数 ×0.75，GPS walking σ ×0.7"""
        t = OrthoRisk()
        assert t.steps_multiplier == 0.75
        assert t.gps_sigma.walking == 0.7

    def test_drift_updates(self):
        """drift 应在达到 drift_update_ticks 后更新，初始值为 0"""
        t = CardiacRisk()
        rng = np.random.default_rng(42)
        assert t.drift_hr == 0.0
        # Drift should update after drift_update_ticks calls
        for _ in range(t.drift_update_ticks):
            t.update_drift(rng)
        assert t.drift_hr != 0.0  # should have changed


# ────────── Events 测试 ──────────

class TestEvents:
    """测试事件的阶段推进、强度曲线、步数倍率和 EventManager 触发逻辑"""

    def test_fever_phases(self):
        """发烧事件应依次经过 onset → peak → recovery 三个阶段"""
        e = FeverEvent(duration_days=10)
        assert e.phase == EventPhase.ONSET
        assert e.intensity == 0.0

        # Advance to peak
        for _ in range(3):
            e.advance_day()
        assert e.phase == EventPhase.PEAK

        # Advance to recovery
        for _ in range(4):
            e.advance_day()
        assert e.phase == EventPhase.RECOVERY

    def test_fever_vital_effect(self):
        """发烧 peak 阶段的瞬时值叠加应全部为正（HR/RR/Temp 升高）"""
        e = FeverEvent(duration_days=10, day_index=3)
        effects = e.vital_effect()
        assert effects["heart_rate"] > 0
        assert effects["resp_rate"] > 0
        assert effects["temperature"] > 0

    def test_injury_steps(self):
        """受伤 peak 阶段步数倍率应小于 0.1（几乎不走路）"""
        e = InjuryEvent(duration_days=10)
        # At peak
        e.day_index = 4
        assert e.phase == EventPhase.PEAK
        assert e.steps_multiplier_value() < 0.1  # almost zero

    def test_event_finishes(self):
        """事件在 advance_day 达到 duration_days 后应标记为 finished"""
        e = FeverEvent(duration_days=3)
        for _ in range(3):
            e.advance_day()
        assert e.is_finished

    def test_event_manager_trigger(self):
        """EventManager 在 200 天内至少应触发一次事件（概率验证）"""
        mgr = EventManager()
        rng = np.random.default_rng(42)
        mgr.set_rng(rng)
        # Call advance_day many times to eventually trigger an event
        triggered = False
        for _ in range(200):
            mgr.advance_day([])
            if mgr.active_event is not None:
                triggered = True
                break
        assert triggered, "EventManager should trigger at least one event in 200 days"

    def test_event_manager_with_traits(self):
        """Traits should increase hazard of certain events"""
        mgr = EventManager()
        rng = np.random.default_rng(0)
        mgr.set_rng(rng)
        traits = [OrthoRisk()]
        # OrthoRisk doubles injury hazard
        triggered_names = []
        for _ in range(500):
            mgr.advance_day(traits)
            if mgr.active_event is not None:
                triggered_names.append(mgr.active_event.name)
        # Should have some events
        assert len(triggered_names) > 0


# ────────── SmartCollar 测试 ──────────

class TestSmartCollar:
    """
    测试 SmartCollar 的完整数据生成流水线。

    覆盖维度：
      - 记录字段完整性和类型正确性
      - 生理指标在合理范围内（HR 30~250, RR 8~80, Temp 36~42）
      - 日步数单调递增和跨天清零
      - 昼夜行为分布差异
      - GPS 在活动期间发生变化
      - Trait 对心率均值的影响
      - 随机种子的可复现性
      - 长时间（1440 ticks = 完整一天）运行稳定性
    """

    def test_record_fields(self):
        """生成的记录应包含完整的 12 个必需字段"""
        collar = SmartCollar(seed=42)
        record = collar.generate_one_record()
        expected_keys = {
            "device_id", "timestamp", "behavior", "heart_rate",
            "resp_rate", "temperature", "steps", "battery",
            "gps_lat", "gps_lng", "event", "event_phase",
        }
        assert set(record.keys()) == expected_keys

    def test_record_types(self):
        """记录中各字段的类型应正确（str/float/int）"""
        collar = SmartCollar(seed=42)
        r = collar.generate_one_record()
        assert isinstance(r["device_id"], str)
        assert isinstance(r["timestamp"], str)
        assert r["behavior"] in ("sleeping", "resting", "walking", "running")
        assert isinstance(r["heart_rate"], float)
        assert isinstance(r["resp_rate"], float)
        assert isinstance(r["temperature"], float)
        assert isinstance(r["steps"], int)
        assert isinstance(r["gps_lat"], float)
        assert isinstance(r["gps_lng"], float)

    def test_vital_ranges(self):
        """100 条记录的生理指标应全部在合法范围内"""
        collar = SmartCollar(seed=42)
        for _ in range(100):
            r = collar.generate_one_record()
            assert 30 <= r["heart_rate"] <= 250
            assert 8 <= r["resp_rate"] <= 80
            assert 36.0 <= r["temperature"] <= 42.0

    def test_steps_monotonic_within_day(self):
        """同一天内，steps 应单调递增（只增不减）"""
        collar = SmartCollar(
            start_time=datetime(2025, 6, 1, 10, 0, 0),
            tick_interval=timedelta(minutes=1),
            seed=42,
        )
        prev_steps = 0
        for _ in range(100):
            r = collar.generate_one_record()
            assert r["steps"] >= prev_steps
            prev_steps = r["steps"]

    def test_steps_reset_on_day_change(self):
        """跨越午夜后，步数应重置（新一天的初始步数小于前一天的最大步数）"""
        collar = SmartCollar(
            profile=DogProfile(dog_id="day_change_test"),
            start_time=datetime(2025, 6, 1, 23, 55, 0),
            tick_interval=timedelta(minutes=5),
            seed=42,
        )
        # Generate records until we cross midnight
        day1_steps: list[int] = []
        day2_steps: list[int] = []
        for _ in range(20):
            r = collar.generate_one_record()
            ts = datetime.fromisoformat(r["timestamp"])
            if ts.date() == datetime(2025, 6, 1).date():
                day1_steps.append(r["steps"])
            else:
                day2_steps.append(r["steps"])
        assert len(day2_steps) > 0, "Should have crossed midnight"
        # After reset, the first step count of day 2 should be
        # less than or equal to the last step count of day 1
        # (unless day 1 had 0 steps, which is fine)
        if day1_steps and max(day1_steps) > 0:
            assert day2_steps[0] < max(day1_steps)

    def test_nighttime_more_sleeping(self):
        """夜间（23:00 开始）300 ticks 内，sleeping 次数应多于 running"""
        collar = SmartCollar(
            start_time=datetime(2025, 6, 1, 23, 0, 0),
            tick_interval=timedelta(minutes=1),
            seed=42,
        )
        counts = Counter()
        for _ in range(300):
            r = collar.generate_one_record()
            counts[r["behavior"]] += 1
        # Night should have sleeping as dominant behavior
        assert counts["sleeping"] > counts["running"]

    def test_daytime_more_active(self):
        """白天（10:00 开始）300 ticks 内，活动行为（walking+running）应多于被动行为"""
        collar = SmartCollar(
            start_time=datetime(2025, 6, 1, 10, 0, 0),
            tick_interval=timedelta(minutes=1),
            seed=42,
        )
        counts = Counter()
        for _ in range(300):
            r = collar.generate_one_record()
            counts[r["behavior"]] += 1
        active = counts["walking"] + counts["running"]
        passive = counts["sleeping"] + counts["resting"]
        assert active > passive

    def test_gps_changes_when_moving(self):
        """白天 200 ticks 后，GPS 坐标应与初始位置不同（狗在活动）"""
        collar = SmartCollar(
            start_time=datetime(2025, 6, 1, 10, 0, 0),
            tick_interval=timedelta(minutes=1),
            seed=42,
        )
        initial_lat = collar._gps_lat
        initial_lng = collar._gps_lng
        # Generate many records during daytime (more movement)
        for _ in range(200):
            collar.generate_one_record()
        # GPS should have changed
        assert (collar._gps_lat != initial_lat) or (collar._gps_lng != initial_lng)

    def test_trait_affects_heart_rate(self):
        """CardiacRisk should raise average heart rate"""
        rng_seed = 42
        # Without traits
        collar_no_trait = SmartCollar(
            profile=DogProfile(dog_id="no_trait"),
            start_time=datetime(2025, 6, 1, 0, 0, 0),
            seed=rng_seed,
        )
        # With CardiacRisk
        collar_cardiac = SmartCollar(
            profile=DogProfile(dog_id="cardiac", traits=[CardiacRisk()]),
            start_time=datetime(2025, 6, 1, 0, 0, 0),
            seed=rng_seed,
        )

        hr_no = [collar_no_trait.generate_one_record()["heart_rate"] for _ in range(200)]
        hr_c = [collar_cardiac.generate_one_record()["heart_rate"] for _ in range(200)]

        assert np.mean(hr_c) > np.mean(hr_no)



    def test_many_records(self):
        """模拟完整一天（1440 分钟 = 1440 ticks）应无错误"""
        collar = SmartCollar(
            start_time=datetime(2025, 6, 1, 0, 0, 0),
            tick_interval=timedelta(minutes=1),
            seed=42,
        )
        for _ in range(1440):
            r = collar.generate_one_record()
            assert r is not None
