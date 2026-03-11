"""
BaseExporter —— 数据输出层的抽象基类（策略模式）

所有 exporter（file_exporter, http_exporter …）都必须继承此类并实现三个抽象方法。
这是策略模式的应用：调度器 (main.py) 只依赖 BaseExporter 接口，
运行时注入具体实现（当前阶段用 FileExporter，未来可替换为 HttpExporter）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseExporter(ABC):
    """
    数据导出器的统一接口。

    子类必须实现：
      - export(record) : 导出一条数据记录
      - flush()        : 强制刷盘 / 发送缓冲区
      - close()        : 释放资源
    """

    @abstractmethod
    def export(self, record: dict) -> None:
        """
        导出一条记录。

        Parameters
        ----------
        record : dict
            由 SmartCollar.generate_one_record() 产出的字典，
            包含 device_id, timestamp, behavior, heart_rate 等 12 个字段
        """

    @abstractmethod
    def flush(self) -> None:
        """强制刷盘 / 发送缓冲区中的所有数据"""

    @abstractmethod
    def close(self) -> None:
        """释放资源（关闭文件句柄 / 断开连接等）"""
