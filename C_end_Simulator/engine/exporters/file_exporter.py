"""
FileExporter —— 把模拟数据写入本地 JSONL 文件

写入目标: output_data/realtime_stream.jsonl
每条记录占一行（JSON Lines 格式），方便 UI 层逐行追加读取。

JSON Lines (JSONL) 格式的优点：
  - 每行是一个独立的 JSON 对象，可以逐行解析
  - 支持追加写入，无需读取整个文件
  - TUI/GUI 可以用 tail -f 的方式实时读取新数据
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from engine.exporters.base_exporter import BaseExporter

# 默认输出路径：C_end_Simulator/output_data/（通过 __file__ 相对定位）
_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output_data"
# 默认输出文件名
_DEFAULT_STREAM_FILE = "realtime_stream.jsonl"


class FileExporter(BaseExporter):
    """
    将 record 以 JSON Lines 格式追加写入文件。

    Parameters
    ----------
    output_dir : str | Path | None
        输出目录，默认为 ``C_end_Simulator/output_data/``
    filename : str
        文件名，默认为 ``realtime_stream.jsonl``

    使用方式：
        exporter = FileExporter()
        exporter.export(record)   # 追加写入一行 JSON
        exporter.flush()          # 强制刷盘
        exporter.close()          # 关闭文件句柄
    """

    def __init__(
        self,
        output_dir: str | Path | None = None,
        filename: str = _DEFAULT_STREAM_FILE,
    ) -> None:
        # 确定输出目录并自动创建（如果不存在）
        self._output_dir = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._filepath = self._output_dir / filename
        # 以追加模式打开文件（不覆盖已有数据）
        self._file = open(self._filepath, "a", encoding="utf-8")

    # ── BaseExporter 接口实现 ──

    def export(self, record: dict) -> None:
        """将一条记录序列化为 JSON 并追加写入文件（每条一行，JSONL 格式）"""
        line = json.dumps(record, ensure_ascii=False)
        self._file.write(line + "\n")

    def flush(self) -> None:
        """强制将缓冲区数据写入磁盘（flush + fsync 确保数据持久化）"""
        self._file.flush()
        os.fsync(self._file.fileno())

    def close(self) -> None:
        """关闭文件句柄（可安全调用多次，幂等操作）"""
        if not self._file.closed:
            self._file.flush()
            self._file.close()

    # ── 便利属性 ──

    @property
    def filepath(self) -> Path:
        """返回当前写入的文件路径"""
        return self._filepath

    def __repr__(self) -> str:
        return f"FileExporter(path={self._filepath})"
