"""
test_step5_tui_backend.py —— TUI 后端接口层测试

测试 ui_tui/backend/ 中的三个接口模块：
  - DataAPI     : 数据读取
  - CommandAPI  : 指令发送
  - UserStore   : 用户管理

所有测试使用 tmp_path 临时目录，不依赖外部引擎运行。
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from ui_tui.backend.data_api import DataAPI
from ui_tui.backend.command_api import CommandAPI
from ui_tui.backend.user_store import UserStore


# ═════════════════════════════════════════════════════════
# DataAPI 测试
# ═════════════════════════════════════════════════════════


class TestDataAPI:
    """DataAPI 数据读取接口测试"""

    def test_get_engine_status_no_file(self, tmp_path: Path) -> None:
        """文件不存在时返回 None"""
        api = DataAPI(output_dir=tmp_path)
        assert api.get_engine_status() is None

    def test_get_engine_status_valid(self, tmp_path: Path) -> None:
        """正常读取 engine_status.json"""
        status = {"running": True, "num_dogs": 2, "current_tick": 50}
        (tmp_path / "engine_status.json").write_text(
            json.dumps(status), encoding="utf-8"
        )
        api = DataAPI(output_dir=tmp_path)
        result = api.get_engine_status()
        assert result is not None
        assert result["running"] is True
        assert result["num_dogs"] == 2
        assert result["current_tick"] == 50

    def test_get_engine_status_empty_file(self, tmp_path: Path) -> None:
        """空文件返回 None"""
        (tmp_path / "engine_status.json").write_text("", encoding="utf-8")
        api = DataAPI(output_dir=tmp_path)
        assert api.get_engine_status() is None

    def test_get_engine_status_invalid_json(self, tmp_path: Path) -> None:
        """无效 JSON 返回 None"""
        (tmp_path / "engine_status.json").write_text("{invalid", encoding="utf-8")
        api = DataAPI(output_dir=tmp_path)
        assert api.get_engine_status() is None

    def test_get_latest_records_no_file(self, tmp_path: Path) -> None:
        """文件不存在时返回空列表"""
        api = DataAPI(output_dir=tmp_path)
        assert api.get_latest_records() == []

    def test_get_latest_records(self, tmp_path: Path) -> None:
        """正常读取 JSONL 记录"""
        records = [
            {"device_id": "dog1", "heart_rate": 80, "timestamp": "T01"},
            {"device_id": "dog2", "heart_rate": 90, "timestamp": "T02"},
            {"device_id": "dog1", "heart_rate": 85, "timestamp": "T03"},
        ]
        lines = "\n".join(json.dumps(r) for r in records) + "\n"
        (tmp_path / "realtime_stream.jsonl").write_text(lines, encoding="utf-8")

        api = DataAPI(output_dir=tmp_path)
        result = api.get_latest_records(2)
        assert len(result) == 2
        # 最新的在前面
        assert result[0]["timestamp"] == "T03"
        assert result[1]["timestamp"] == "T02"

    def test_get_records_by_user(self, tmp_path: Path) -> None:
        """按用户 ID 筛选记录"""
        records = [
            {"user_id": "u1", "device_id": "d1", "heart_rate": 80},
            {"user_id": "u2", "device_id": "d2", "heart_rate": 90},
            {"user_id": "u1", "device_id": "d1", "heart_rate": 85},
        ]
        lines = "\n".join(json.dumps(r) for r in records) + "\n"
        (tmp_path / "realtime_stream.jsonl").write_text(lines, encoding="utf-8")

        api = DataAPI(output_dir=tmp_path)
        result = api.get_records_by_user("u1")
        assert len(result) == 2
        assert all(r["user_id"] == "u1" for r in result)

    def test_get_records_by_device(self, tmp_path: Path) -> None:
        """按设备 ID 筛选记录"""
        records = [
            {"device_id": "d1", "heart_rate": 80},
            {"device_id": "d2", "heart_rate": 90},
            {"device_id": "d1", "heart_rate": 85},
        ]
        lines = "\n".join(json.dumps(r) for r in records) + "\n"
        (tmp_path / "realtime_stream.jsonl").write_text(lines, encoding="utf-8")

        api = DataAPI(output_dir=tmp_path)
        result = api.get_records_by_device("d1")
        assert len(result) == 2
        assert all(r["device_id"] == "d1" for r in result)

    def test_get_total_record_count(self, tmp_path: Path) -> None:
        """统计记录总数"""
        records = [
            {"device_id": "d1"},
            {"device_id": "d2"},
            {"device_id": "d1"},
        ]
        lines = "\n".join(json.dumps(r) for r in records) + "\n"
        (tmp_path / "realtime_stream.jsonl").write_text(lines, encoding="utf-8")

        api = DataAPI(output_dir=tmp_path)
        assert api.get_total_record_count() == 3

    def test_get_unique_devices(self, tmp_path: Path) -> None:
        """获取唯一设备 ID"""
        records = [
            {"device_id": "d1"},
            {"device_id": "d2"},
            {"device_id": "d1"},
            {"device_id": "d3"},
        ]
        lines = "\n".join(json.dumps(r) for r in records) + "\n"
        (tmp_path / "realtime_stream.jsonl").write_text(lines, encoding="utf-8")

        api = DataAPI(output_dir=tmp_path)
        devices = api.get_unique_devices()
        assert set(devices) == {"d1", "d2", "d3"}


# ═════════════════════════════════════════════════════════
# CommandAPI 测试
# ═════════════════════════════════════════════════════════


class TestCommandAPI:
    """CommandAPI 指令发送接口测试"""

    def test_send_stop(self, tmp_path: Path) -> None:
        """发送 stop 指令"""
        api = CommandAPI(output_dir=tmp_path)
        api.send_stop()
        cmd = json.loads((tmp_path / "command.json").read_text(encoding="utf-8"))
        assert cmd["action"] == "stop"

    def test_send_pause(self, tmp_path: Path) -> None:
        """发送 pause 指令"""
        api = CommandAPI(output_dir=tmp_path)
        api.send_pause()
        cmd = json.loads((tmp_path / "command.json").read_text(encoding="utf-8"))
        assert cmd["action"] == "pause"

    def test_send_resume(self, tmp_path: Path) -> None:
        """发送 resume 指令"""
        api = CommandAPI(output_dir=tmp_path)
        api.send_resume()
        cmd = json.loads((tmp_path / "command.json").read_text(encoding="utf-8"))
        assert cmd["action"] == "resume"

    def test_send_set_interval(self, tmp_path: Path) -> None:
        """发送 set_interval 指令"""
        api = CommandAPI(output_dir=tmp_path)
        api.send_set_interval(2.5)
        cmd = json.loads((tmp_path / "command.json").read_text(encoding="utf-8"))
        assert cmd["action"] == "set_interval"
        assert cmd["value"] == 2.5

    def test_send_set_interval_negative_raises(self, tmp_path: Path) -> None:
        """负数间隔应抛出异常"""
        api = CommandAPI(output_dir=tmp_path)
        with pytest.raises(ValueError):
            api.send_set_interval(-1.0)

    def test_clear_command(self, tmp_path: Path) -> None:
        """清空指令文件"""
        api = CommandAPI(output_dir=tmp_path)
        api.send_stop()
        api.clear_command()
        text = (tmp_path / "command.json").read_text(encoding="utf-8")
        assert text == ""

    def test_get_current_command(self, tmp_path: Path) -> None:
        """读取当前指令"""
        api = CommandAPI(output_dir=tmp_path)
        api.send_pause()
        cmd = api.get_current_command()
        assert cmd is not None
        assert cmd["action"] == "pause"

    def test_get_current_command_empty(self, tmp_path: Path) -> None:
        """无指令时返回 None"""
        api = CommandAPI(output_dir=tmp_path)
        assert api.get_current_command() is None


# ═════════════════════════════════════════════════════════
# UserStore 测试
# ═════════════════════════════════════════════════════════


class TestUserStore:
    """UserStore 用户管理接口测试"""

    def test_login_creates_user_id(self) -> None:
        """登录生成 user_id"""
        store = UserStore()
        user_id = store.login("alice", 3)
        assert user_id.startswith("user_")
        assert len(user_id) == 13  # "user_" + 8 hex chars

    def test_login_deterministic(self) -> None:
        """相同用户名产生相同 user_id"""
        store1 = UserStore()
        store2 = UserStore()
        assert store1.login("bob", 1) == store2.login("bob", 2)

    def test_login_different_users(self) -> None:
        """不同用户名产生不同 user_id"""
        store = UserStore()
        id1 = store.login("alice", 1)
        store.logout()
        id2 = store.login("bob", 1)
        assert id1 != id2

    def test_login_sets_session(self) -> None:
        """登录后会话状态正确"""
        store = UserStore()
        store.login("charlie", 5)
        assert store.is_logged_in
        assert store.username == "charlie"
        assert store.num_dogs == 5

    def test_logout_clears_session(self) -> None:
        """登出后会话清除"""
        store = UserStore()
        store.login("charlie", 5)
        store.logout()
        assert not store.is_logged_in
        assert store.user_id == ""
        assert store.num_dogs == 0

    def test_get_user_info(self) -> None:
        """获取用户信息字典"""
        store = UserStore()
        store.login("dave", 2)
        info = store.get_user_info()
        assert info is not None
        assert info["username"] == "dave"
        assert info["num_dogs"] == 2
        assert info["logged_in"] is True

    def test_get_user_info_not_logged_in(self) -> None:
        """未登录时返回 None"""
        store = UserStore()
        assert store.get_user_info() is None

    def test_login_empty_username_raises(self) -> None:
        """空用户名应抛出异常"""
        store = UserStore()
        with pytest.raises(ValueError):
            store.login("", 1)

    def test_login_zero_dogs_raises(self) -> None:
        """0 只狗应抛出异常"""
        store = UserStore()
        with pytest.raises(ValueError):
            store.login("alice", 0)

    def test_login_negative_dogs_raises(self) -> None:
        """负数狗应抛出异常"""
        store = UserStore()
        with pytest.raises(ValueError):
            store.login("alice", -1)


# ═════════════════════════════════════════════════════════
# 集成测试：Engine → DataAPI 数据流
# ═════════════════════════════════════════════════════════


class TestIntegrationEngineToTUI:
    """测试从 Engine 生成数据到 TUI 后端读取的完整数据流"""

    def test_engine_data_readable_by_data_api(self, tmp_path: Path) -> None:
        """Engine 输出的数据能被 DataAPI 正确读取"""
        from engine.main import run

        records = run(
            num_dogs=2, num_ticks=5, seed=42,
            output_dir=str(tmp_path),
        )
        assert len(records) == 10  # 2 dogs × 5 ticks

        api = DataAPI(output_dir=tmp_path)

        # 验证引擎状态可读
        status = api.get_engine_status()
        assert status is not None
        assert status["running"] is False  # 引擎已结束
        assert status["num_dogs"] == 2

        # 验证记录可读
        latest = api.get_latest_records(10)
        assert len(latest) == 10

        # 验证设备可列举
        devices = api.get_unique_devices()
        assert len(devices) == 2

    def test_command_api_writes_for_engine(self, tmp_path: Path) -> None:
        """CommandAPI 写入的指令格式与 Engine 读取兼容"""
        from engine.main import read_command

        cmd_api = CommandAPI(output_dir=tmp_path)
        cmd_api.send_pause()

        # 使用 engine 的 read_command 函数验证兼容性
        cmd = read_command(tmp_path)
        assert cmd is not None
        assert cmd["action"] == "pause"

    def test_full_tui_backend_workflow(self, tmp_path: Path) -> None:
        """完整的 TUI 后端工作流：登录 → 数据读取 → 发送指令"""
        from engine.main import run

        # 1) 用户登录
        store = UserStore(output_dir=tmp_path)
        user_id = store.login("test_user", 2)
        assert store.is_logged_in
        assert store.num_dogs == 2

        # 2) 引擎生成数据
        run(num_dogs=2, num_ticks=5, seed=42, output_dir=str(tmp_path))

        # 3) TUI 读取数据
        data_api = DataAPI(output_dir=tmp_path)
        status = data_api.get_engine_status()
        assert status is not None
        records = data_api.get_latest_records(10)
        assert len(records) == 10

        # 4) TUI 发送控制指令
        cmd_api = CommandAPI(output_dir=tmp_path)
        cmd_api.send_set_interval(2.0)
        cmd = cmd_api.get_current_command()
        assert cmd is not None
        assert cmd["action"] == "set_interval"
        assert cmd["value"] == 2.0

        # 5) 用户登出
        store.logout()
        assert not store.is_logged_in
