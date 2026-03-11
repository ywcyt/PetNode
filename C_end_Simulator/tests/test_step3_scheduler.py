"""
Step 3 测试：验证调度器能串起 SmartCollar → FileExporter

测试范围（对应开发流程第三步）：
  - parse_args     : 命令行参数解析（默认值和自定义值）
  - command.json   : 控制指令读写（不存在/空文件/合法/非法 JSON）
  - engine_status  : 引擎状态文件写入
  - BaseListener   : 抽象类不可直接实例化
  - DummyListener  : poll 返回 None、close 幂等、repr
  - run() 调度器   : 单狗/多狗记录数、字段完整性、JSONL 输出、
                     engine_status 创建、stop 指令处理、
                     多狗 device_id 唯一性、随机种子可复现性、
                     零 ticks 边界情况
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from engine.main import run, parse_args, read_command, write_engine_status
from engine.listeners.base_listener import BaseListener
from engine.listeners.dummy_listener import DummyListener


# ────────── parse_args 测试 ──────────

class TestParseArgs:
    """测试命令行参数解析的默认值和自定义值"""

    def test_defaults(self):
        """不传参时应使用默认值：1 只狗、100 ticks、1 分钟/tick、0 间隔"""
        args = parse_args([])
        assert args.dogs == 1
        assert args.ticks == 100
        assert args.tick_minutes == 1
        assert args.interval == 0.0
        assert args.seed is None
        assert args.output_dir is None
        assert args.log_level == "INFO"

    def test_custom_args(self):
        """自定义参数应被正确解析"""
        args = parse_args([
            "--dogs", "3",
            "--ticks", "50",
            "--tick-minutes", "15",
            "--interval", "0.5",
            "--seed", "42",
            "--output-dir", "/tmp/test_out",
            "--log-level", "DEBUG",
        ])
        assert args.dogs == 3
        assert args.ticks == 50
        assert args.tick_minutes == 15
        assert args.interval == 0.5
        assert args.seed == 42
        assert args.output_dir == "/tmp/test_out"
        assert args.log_level == "DEBUG"


# ────────── command.json 测试 ──────────

class TestCommandJson:
    """测试 command.json 控制指令的读写功能（引擎与 UI 之间的通信机制）"""
    def test_read_no_file(self, tmp_path: Path):
        """不存在 command.json 时返回 None"""
        assert read_command(tmp_path) is None

    def test_read_empty_file(self, tmp_path: Path):
        """空文件时返回 None"""
        (tmp_path / "command.json").write_text("", encoding="utf-8")
        assert read_command(tmp_path) is None

    def test_read_valid_command(self, tmp_path: Path):
        """合法 JSON 能正常解析"""
        cmd = {"action": "stop"}
        (tmp_path / "command.json").write_text(
            json.dumps(cmd), encoding="utf-8",
        )
        result = read_command(tmp_path)
        assert result == cmd

    def test_read_invalid_json(self, tmp_path: Path):
        """非法 JSON 返回 None（不抛异常）"""
        (tmp_path / "command.json").write_text("{bad json", encoding="utf-8")
        assert read_command(tmp_path) is None

    def test_write_engine_status(self, tmp_path: Path):
        """写入 engine_status.json"""
        status = {"running": True, "current_tick": 10}
        write_engine_status(tmp_path, status)
        path = tmp_path / "engine_status.json"
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["running"] is True
        assert loaded["current_tick"] == 10


# ────────── BaseListener 测试 ──────────

class TestBaseListener:
    """验证 BaseListener 作为抽象基类不能直接实例化"""
    def test_cannot_instantiate(self):
        """BaseListener 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError):
            BaseListener()  # type: ignore[abstract]


# ────────── DummyListener 测试 ──────────

class TestDummyListener:
    """测试 DummyListener 的占位行为（poll 返回 None、close 幂等）"""
    def test_poll_returns_none(self):
        """DummyListener.poll() 应返回 None"""
        listener = DummyListener()
        assert listener.poll() is None

    def test_close_is_idempotent(self):
        """close() 可安全调用多次"""
        listener = DummyListener()
        listener.close()
        listener.close()  # 不应抛异常

    def test_repr(self):
        listener = DummyListener()
        assert "DummyListener" in repr(listener)


# ────────── run() 调度器集成测试 ──────────

class TestSchedulerRun:
    """
    调度器集成测试——验证 run() 函数能正确串联 SmartCollar → FileExporter 的完整流程。

    测试维度：
      - 记录数量正确性（单狗/多狗 × ticks 数）
      - 记录字段完整性
      - JSONL 输出文件创建和内容合法性
      - engine_status.json 状态记录
      - command.json stop 指令处理
      - 多狗 device_id 唯一性
      - 随机种子可复现性
      - 边界情况（0 ticks）
    """
    def test_single_dog_generates_records(self, tmp_path: Path):
        """1 只狗、10 ticks 应产出 10 条记录"""
        records = run(
            num_dogs=1, num_ticks=10, seed=42,
            output_dir=tmp_path,
        )
        assert len(records) == 10

    def test_multi_dog_generates_records(self, tmp_path: Path):
        """3 只狗、5 ticks 应产出 15 条记录"""
        records = run(
            num_dogs=3, num_ticks=5, seed=42,
            output_dir=tmp_path,
        )
        assert len(records) == 15

    def test_records_have_correct_fields(self, tmp_path: Path):
        """每条记录都包含 12 个必需字段"""
        expected_keys = {
            "device_id", "timestamp", "behavior", "heart_rate",
            "resp_rate", "temperature", "steps", "battery",
            "gps_lat", "gps_lng", "event", "event_phase",
        }
        records = run(num_dogs=1, num_ticks=5, seed=42, output_dir=tmp_path)
        for r in records:
            assert set(r.keys()) == expected_keys

    def test_output_file_created(self, tmp_path: Path):
        """运行后应创建 JSONL 输出文件"""
        run(num_dogs=1, num_ticks=5, seed=42, output_dir=tmp_path)
        jsonl = tmp_path / "realtime_stream.jsonl"
        assert jsonl.exists()
        lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 5

    def test_output_is_valid_jsonl(self, tmp_path: Path):
        """输出文件每行都是合法 JSON"""
        run(num_dogs=2, num_ticks=10, seed=42, output_dir=tmp_path)
        jsonl = tmp_path / "realtime_stream.jsonl"
        lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 20
        for line in lines:
            parsed = json.loads(line)
            assert "device_id" in parsed

    def test_engine_status_written(self, tmp_path: Path):
        """运行后应创建 engine_status.json"""
        run(num_dogs=1, num_ticks=10, seed=42, output_dir=tmp_path)
        status_path = tmp_path / "engine_status.json"
        assert status_path.exists()
        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["running"] is False
        assert status["current_tick"] == 10

    def test_stop_command(self, tmp_path: Path):
        """command.json 写入 stop 指令应提前终止"""
        # 写入 stop 指令
        cmd_path = tmp_path / "command.json"
        cmd_path.write_text(
            json.dumps({"action": "stop"}), encoding="utf-8",
        )
        records = run(
            num_dogs=1, num_ticks=1000, seed=42,
            output_dir=tmp_path,
        )
        # 应该提前停止（第一个 tick 就读到 stop）
        assert len(records) == 0

    def test_multi_dog_different_ids(self, tmp_path: Path):
        """多只狗应有不同的 device_id"""
        records = run(num_dogs=3, num_ticks=1, seed=42, output_dir=tmp_path)
        ids = {r["device_id"] for r in records}
        assert len(ids) == 3

    def test_reproducible_with_seed(self, tmp_path: Path):
        """相同种子应产出相同数值（device_id 除外，因 uuid4 不受 NumPy 种子控制）"""
        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"
        r1 = run(num_dogs=1, num_ticks=20, seed=42, output_dir=dir1)
        r2 = run(num_dogs=1, num_ticks=20, seed=42, output_dir=dir2)
        # device_id 由 uuid4 生成，不受 numpy seed 控制，需排除比较
        for a, b in zip(r1, r2):
            for key in a:
                if key == "device_id":
                    continue
                assert a[key] == b[key], f"key={key}: {a[key]} != {b[key]}"

    def test_zero_ticks(self, tmp_path: Path):
        """0 ticks 应返回空列表"""
        records = run(num_dogs=1, num_ticks=0, seed=42, output_dir=tmp_path)
        assert len(records) == 0
