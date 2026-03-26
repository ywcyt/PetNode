"""
FileStorage —— 将接收到的数据保存为本地 JSONL 文件

当前阶段（第三周）的存储实现，满足老师要求的"保存到文件"。
数据以 JSON Lines 格式写入，每条记录占一行，方便后续逐行读取和分析。

与 Engine 端 FileExporter 的区别：
  - FileExporter   在 Engine 容器内，保存 Engine 自己生成的数据（客户端本地备份）
  - FileStorage    在 Flask 容器内，保存通过 HTTP 接收到的数据（服务端持久化）
  - 两者互不相关，数据存在各自容器的独立文件系统中

未来替换为 MysqlStorage 时，只需在 app.py 中修改一行 import 即可，
本文件无需改动、无需删除（可保留为备用/降级方案）。

文件存储路径：
  容器内: /app/data/received.jsonl（通过 DATA_DIR 环境变量配置）
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

# Use a package-relative import to avoid unresolved reference when module is imported
from .base_storage import BaseStorage

logger = logging.getLogger("storage.file")

# 默认数据存储目录（容器内路径，可通过构造函数参数覆盖）
_DEFAULT_DATA_DIR = "/app/data"

# 默认数据文件名（JSON Lines 格式，每行一条 JSON 记录）
_DEFAULT_FILENAME = "received.jsonl"


class FileStorage(BaseStorage):
    """将接收到的记录追加写入 JSON Lines 文件。

    行为要点：
    - 线程安全：内部使用 threading.Lock 保护对文件的写入。
    - 可配置：可以通过 DATA_DIR 环境变量或构造函数传入 data_dir。
    - 持久化：每次写入会 flush 并调用 os.fsync 确保数据写入磁盘（尽可能保证持久性）。

    注意：在高吞吐或性能敏感场景，fsync 会降低性能；但当前作业需求偏可靠性，保留 fsync。
    """

    def __init__(self, data_dir: Optional[str] = None, filename: str = _DEFAULT_FILENAME):
        # 允许外部通过构造函数覆盖，也会优先读取环境变量
        env_dir = os.environ.get("DATA_DIR")
        chosen_dir = data_dir or env_dir or _DEFAULT_DATA_DIR

        self.data_dir = Path(chosen_dir)
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.exception("无法创建数据目录: %s", self.data_dir)
            raise

        self.file_path = self.data_dir / filename
        # 以追加模式打开文本文件，确保使用 utf-8 编码
        try:
            # buffering=1 => line buffered on text mode; we'll still call flush/fsync explicitly
            self._file = open(self.file_path, "a", encoding="utf-8", buffering=1)
        except Exception:
            logger.exception("无法打开数据文件用于追加: %s", self.file_path)
            raise

        self._lock = threading.Lock()
        logger.info("FileStorage initialized, writing to %s", self.file_path)

    def save(self, record: dict) -> None:
        """保存一条数据记录到 JSONL 文件。

        Raises Exception on failure so caller (app.py) can convert to 500.
        """
        if not isinstance(record, dict):
            raise TypeError("record must be a dict")

        line = json.dumps(record, ensure_ascii=False)

        with self._lock:
            try:
                self._file.write(line + "\n")
                self._file.flush()
                try:
                    os.fsync(self._file.fileno())
                except OSError:
                    # 如果底层文件系统不支持 fsync（例如某些 windows pipes），仅记录但不抛出
                    logger.debug("fsync not supported or failed for %s", self.file_path, exc_info=True)
            except Exception:
                logger.exception("写入数据到 %s 失败", self.file_path)
                raise

    def close(self) -> None:
        """关闭文件句柄，释放资源。"""
        try:
            with self._lock:
                if not self._file.closed:
                    self._file.close()
                    logger.info("Closed storage file %s", self.file_path)
        except Exception:
            logger.exception("关闭数据文件时出错: %s", self.file_path)
            raise
