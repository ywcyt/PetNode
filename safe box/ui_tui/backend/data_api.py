"""
data_api.py —— TUI 后端数据读取接口

职责：
  - 读取 engine_status.json：获取引擎运行状态
  - 读取 realtime_stream.jsonl：获取最新的模拟数据记录
  - 为 TUI 前端提供统一、类型安全的数据访问方法

所有文件 I/O 逻辑封装在此，TUI 前端无需直接操作文件系统。

用法::

    api = DataAPI(output_dir="/app/output_data")
    status = api.get_engine_status()       # -> dict | None
    records = api.get_latest_records(20)   # -> list[dict]
    records = api.get_records_by_user("user_abc123")  # -> list[dict]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


# 默认输出目录（Docker 内: /app/output_data，本地: C_end_Simulator/output_data/）
_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output_data"


class DataAPI:
    """
    TUI 后端数据读取接口。

    Parameters
    ----------
    output_dir : str | Path | None
        output_data 目录路径，默认为 ``C_end_Simulator/output_data/``
    """

    def __init__(self, output_dir: str | Path | None = None) -> None:
        self._output_dir = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR

    @property
    def output_dir(self) -> Path:
        """返回当前数据目录路径"""
        return self._output_dir

    # ────────────────── 引擎状态 ──────────────────

    def get_engine_status(self) -> Optional[dict]:
        """
        读取 engine_status.json，返回引擎运行状态。

        Returns
        -------
        dict | None
            引擎状态字典，包含 running, num_users, num_dogs, total_ticks,
            tick_minutes, current_tick 等字段。
            文件不存在或解析失败时返回 None。
        """
        status_path = self._output_dir / "engine_status.json"
        if not status_path.exists():
            return None
        try:
            text = status_path.read_text(encoding="utf-8").strip()
            if not text:
                return None
            return json.loads(text)
        except (json.JSONDecodeError, OSError):
            return None

    # ────────────────── 实时数据流 ──────────────────

    def get_latest_records(self, n: int = 20) -> list[dict]:
        """
        从 realtime_stream.jsonl 读取最新的 n 条记录。

        Parameters
        ----------
        n : int
            返回的最大记录数量（默认 20）

        Returns
        -------
        list[dict]
            最近 n 条记录（时间倒序，最新在前）
        """
        stream_path = self._output_dir / "realtime_stream.jsonl"
        if not stream_path.exists():
            return []
        try:
            lines = stream_path.read_text(encoding="utf-8").strip().splitlines()
            records = []
            # 从尾部倒着解析，取最新的 n 条
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(records) >= n:
                    break
            return records
        except OSError:
            return []

    def get_records_by_user(
        self,
        user_id: str,
        n: int = 50,
    ) -> list[dict]:
        """
        获取指定用户的最新记录。

        Parameters
        ----------
        user_id : str
            用户 ID
        n : int
            返回的最大记录数量（默认 50）

        Returns
        -------
        list[dict]
            该用户的最近 n 条记录（时间倒序）
        """
        all_records = self.get_latest_records(n * 5)
        user_records = [r for r in all_records if r.get("user_id") == user_id]
        return user_records[:n]

    def get_records_by_device(
        self,
        device_id: str,
        n: int = 20,
    ) -> list[dict]:
        """
        获取指定设备（狗）的最新记录。

        Parameters
        ----------
        device_id : str
            设备 ID（即 dog_id）
        n : int
            返回的最大记录数量（默认 20）

        Returns
        -------
        list[dict]
            该设备的最近 n 条记录（时间倒序）
        """
        all_records = self.get_latest_records(n * 5)
        dev_records = [r for r in all_records if r.get("device_id") == device_id]
        return dev_records[:n]

    def get_total_record_count(self) -> int:
        """
        获取 realtime_stream.jsonl 中的总记录行数。

        Returns
        -------
        int
            记录总数
        """
        stream_path = self._output_dir / "realtime_stream.jsonl"
        if not stream_path.exists():
            return 0
        try:
            count = 0
            with open(stream_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        count += 1
            return count
        except OSError:
            return 0

    def get_unique_devices(self) -> list[str]:
        """
        获取数据流中出现过的所有设备 ID 列表（去重）。

        Returns
        -------
        list[str]
            设备 ID 列表
        """
        records = self.get_latest_records(500)
        seen: set[str] = set()
        result: list[str] = []
        for r in records:
            did = r.get("device_id", "")
            if did and did not in seen:
                seen.add(did)
                result.append(did)
        return result

    def __repr__(self) -> str:
        return f"DataAPI(output_dir={self._output_dir})"
