"""
Step 4 测试 B：模块健康检查

测试范围：
  - 每个模块能否正常导入（import smoke test）
  - 每个核心类能否正常实例化
  - 模块间依赖关系是否正确
  - engine 完整流程能否从头到尾跑通（端到端冒烟测试）
  - output_data 目录结构完整性
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


# ────────── 模块导入测试 ──────────


class TestModuleImports:
    """验证每个模块能被正常导入（import smoke test）"""

    @pytest.mark.parametrize("module_name", [
        "engine.models",
        "engine.models.dog_profile",
        "engine.models.smart_collar",
        "engine.traits",
        "engine.traits.base_trait",
        "engine.traits.cardiac",
        "engine.traits.respiratory",
        "engine.traits.ortho",
        "engine.events",
        "engine.events.base_event",
        "engine.events.event_manager",
        "engine.events.fever",
        "engine.events.injury",
        "engine.exporters",
        "engine.exporters.base_exporter",
        "engine.exporters.file_exporter",
        "engine.listeners",
        "engine.listeners.base_listener",
        "engine.listeners.dummy_listener",
        "engine.main",
    ])
    def test_import_module(self, module_name: str):
        """每个 engine 子模块应能成功导入"""
        mod = importlib.import_module(module_name)
        assert mod is not None


# ────────── 核心类实例化测试 ──────────


class TestClassInstantiation:
    """验证每个核心类能被正常实例化"""

    def test_dog_profile_instantiation(self):
        """DogProfile 应能成功创建默认实例"""
        from engine.models.dog_profile import DogProfile
        p = DogProfile()
        assert p.dog_id is not None
        assert p.breed_size == "medium"

    def test_dog_profile_random(self):
        """DogProfile.random_profile() 应能创建随机实例"""
        import numpy as np
        from engine.models.dog_profile import DogProfile
        rng = np.random.default_rng(42)
        p = DogProfile.random_profile(rng)
        assert p.dog_id is not None
        assert len(p.dog_id) == 12

    def test_smart_collar_instantiation(self):
        """SmartCollar 应能创建默认实例并生成记录"""
        from engine.models.smart_collar import SmartCollar
        collar = SmartCollar(seed=42)
        record = collar.generate_one_record()
        assert record is not None
        assert "heart_rate" in record

    def test_cardiac_risk_instantiation(self):
        """CardiacRisk trait 应能成功创建"""
        from engine.traits.cardiac import CardiacRisk
        t = CardiacRisk()
        assert t.baseline.heart_rate_mean_offset == 10.0

    def test_respiratory_risk_instantiation(self):
        """RespiratoryRisk trait 应能成功创建"""
        from engine.traits.respiratory import RespiratoryRisk
        t = RespiratoryRisk()
        assert t.baseline.resp_rate_mean_offset == 4.0

    def test_ortho_risk_instantiation(self):
        """OrthoRisk trait 应能成功创建"""
        from engine.traits.ortho import OrthoRisk
        t = OrthoRisk()
        assert t.steps_multiplier == 0.75

    def test_fever_event_instantiation(self):
        """FeverEvent 应能成功创建"""
        from engine.events.fever import FeverEvent
        e = FeverEvent(duration_days=7)
        assert e is not None
        assert e.duration_days == 7

    def test_injury_event_instantiation(self):
        """InjuryEvent 应能成功创建"""
        from engine.events.injury import InjuryEvent
        e = InjuryEvent(duration_days=10)
        assert e is not None
        assert e.duration_days == 10

    def test_event_manager_instantiation(self):
        """EventManager 应能成功创建"""
        from engine.events.event_manager import EventManager
        mgr = EventManager()
        assert mgr.active_event is None

    def test_file_exporter_instantiation(self, tmp_path: Path):
        """FileExporter 应能成功创建并写入"""
        from engine.exporters.file_exporter import FileExporter
        exporter = FileExporter(output_dir=tmp_path)
        exporter.export({"test": True})
        exporter.close()
        assert exporter.filepath.exists()

    def test_dummy_listener_instantiation(self):
        """DummyListener 应能成功创建"""
        from engine.listeners.dummy_listener import DummyListener
        listener = DummyListener()
        assert listener.poll() is None
        listener.close()


# ────────── 端到端冒烟测试 ──────────


class TestEndToEndSmoke:
    """端到端冒烟测试：验证 engine 完整流程能从头到尾跑通"""

    def test_full_pipeline_smoke(self, tmp_path: Path):
        """
        完整流程冒烟测试：
        创建项圈 → 生成数据 → 导出到文件 → 验证输出
        """
        from engine.models.smart_collar import SmartCollar
        from engine.exporters.file_exporter import FileExporter

        collar = SmartCollar(seed=42)
        exporter = FileExporter(output_dir=tmp_path)

        for _ in range(10):
            record = collar.generate_one_record()
            exporter.export(record)

        exporter.flush()
        exporter.close()

        # 验证文件内容
        lines = exporter.filepath.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 10
        for line in lines:
            parsed = json.loads(line)
            assert "device_id" in parsed
            assert "heart_rate" in parsed
            assert "timestamp" in parsed

    def test_run_function_smoke(self, tmp_path: Path):
        """run() 函数端到端冒烟测试"""
        from engine.main import run
        records = run(
            num_dogs=2,
            num_ticks=10,
            seed=42,
            output_dir=tmp_path,
        )
        assert len(records) == 20

        # 验证 JSONL 文件
        jsonl = tmp_path / "realtime_stream.jsonl"
        assert jsonl.exists()

        # 验证 engine_status.json
        status_path = tmp_path / "engine_status.json"
        assert status_path.exists()
        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["running"] is False

    def test_trait_pipeline_smoke(self, tmp_path: Path):
        """带 Trait 的项圈端到端冒烟测试"""
        from engine.models.dog_profile import DogProfile
        from engine.models.smart_collar import SmartCollar
        from engine.exporters.file_exporter import FileExporter
        from engine.traits import CardiacRisk, RespiratoryRisk, OrthoRisk

        # 创建三只不同 Trait 的狗
        profiles = [
            DogProfile(dog_id="cardiac_dog", traits=[CardiacRisk()]),
            DogProfile(dog_id="respiratory_dog", traits=[RespiratoryRisk()]),
            DogProfile(dog_id="ortho_dog", traits=[OrthoRisk()]),
        ]

        exporter = FileExporter(output_dir=tmp_path)
        for i, profile in enumerate(profiles):
            collar = SmartCollar(profile=profile, seed=i * 100)
            for _ in range(10):
                record = collar.generate_one_record()
                exporter.export(record)

        exporter.flush()
        exporter.close()

        lines = exporter.filepath.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 30  # 3 dogs × 10 ticks
