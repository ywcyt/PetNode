"""
Step 2 测试：验证数据能正确写入文件

测试范围（对应开发流程第二步）：
  - BaseExporter  : 抽象类不可直接实例化
  - FileExporter  : JSONL 文件创建、写入格式正确性、追加模式、
                    flush 持久化、自定义文件名、自动创建目录、
                    与 SmartCollar 的集成、close 幂等性
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from engine.exporters.base_exporter import BaseExporter
from engine.exporters.file_exporter import FileExporter
from engine.models.smart_collar import SmartCollar


# ────────── BaseExporter 测试 ──────────

class TestBaseExporter:
    """验证 BaseExporter 作为抽象基类不能直接实例化"""

    def test_cannot_instantiate(self):
        """BaseExporter 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError):
            BaseExporter()  # type: ignore[abstract]


# ────────── FileExporter 测试 ──────────

class TestFileExporter:
    """
    验证 FileExporter 的 JSONL 文件写入功能。

    包括：文件创建、写入格式、追加模式、flush 持久化、
    自定义文件名、自动创建目录、与 SmartCollar 集成、close 幂等。
    """
    def test_export_creates_file(self, tmp_path: Path):
        """export() 应该创建 JSONL 文件"""
        exporter = FileExporter(output_dir=tmp_path)
        record = {"device_id": "test123", "timestamp": "2025-06-01T00:15:00"}
        exporter.export(record)
        exporter.close()
        assert exporter.filepath.exists()

    def test_export_writes_valid_jsonl(self, tmp_path: Path):
        """每行应该是合法的 JSON"""
        exporter = FileExporter(output_dir=tmp_path)
        records = [
            {"device_id": "aaa", "timestamp": "2025-06-01T00:15:00", "heart_rate": 70.0},
            {"device_id": "bbb", "timestamp": "2025-06-01T00:30:00", "heart_rate": 80.0},
        ]
        for r in records:
            exporter.export(r)
        exporter.close()

        lines = exporter.filepath.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        for i, line in enumerate(lines):
            parsed = json.loads(line)
            assert parsed["device_id"] == records[i]["device_id"]

    def test_export_appends(self, tmp_path: Path):
        """多次打开同一文件应追加，不覆盖"""
        filepath = tmp_path / "realtime_stream.jsonl"
        ex1 = FileExporter(output_dir=tmp_path)
        ex1.export({"a": 1})
        ex1.close()

        ex2 = FileExporter(output_dir=tmp_path)
        ex2.export({"b": 2})
        ex2.close()

        lines = filepath.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_flush_persists_data(self, tmp_path: Path):
        """flush() 后数据应可在磁盘读到"""
        exporter = FileExporter(output_dir=tmp_path)
        exporter.export({"x": 42})
        exporter.flush()

        content = exporter.filepath.read_text(encoding="utf-8").strip()
        assert json.loads(content)["x"] == 42
        exporter.close()

    def test_custom_filename(self, tmp_path: Path):
        """可以指定自定义文件名"""
        exporter = FileExporter(output_dir=tmp_path, filename="custom.jsonl")
        exporter.export({"k": "v"})
        exporter.close()
        assert (tmp_path / "custom.jsonl").exists()

    def test_creates_output_dir(self, tmp_path: Path):
        """如果输出目录不存在，应自动创建"""
        nested = tmp_path / "a" / "b" / "c"
        exporter = FileExporter(output_dir=nested)
        exporter.export({"hello": "world"})
        exporter.close()
        assert nested.exists()

    def test_integration_with_smart_collar(self, tmp_path: Path):
        """SmartCollar 生成的数据可以通过 FileExporter 写入文件"""
        collar = SmartCollar(
            start_time=datetime(2025, 6, 1, 0, 0, 0),
            tick_interval=timedelta(minutes=15),
            seed=42,
        )
        exporter = FileExporter(output_dir=tmp_path)

        n_ticks = 5
        for _ in range(n_ticks):
            record = collar.generate_one_record()
            exporter.export(record)
        exporter.close()

        lines = exporter.filepath.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == n_ticks

        # 验证每行都可解析，且包含所有必需字段
        expected_keys = {
            "device_id", "timestamp", "behavior", "heart_rate",
            "resp_rate", "temperature", "steps", "battery",
            "gps_lat", "gps_lng", "event", "event_phase",
        }
        for line in lines:
            parsed = json.loads(line)
            assert set(parsed.keys()) == expected_keys

    def test_close_is_idempotent(self, tmp_path: Path):
        """close() 可以安全调用多次"""
        exporter = FileExporter(output_dir=tmp_path)
        exporter.export({"ok": True})
        exporter.close()
        exporter.close()  # 不应抛异常
