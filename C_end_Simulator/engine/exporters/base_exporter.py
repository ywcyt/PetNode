"""
BaseExporter —— 数据输出层的抽象基类

所有 exporter（file_exporter, http_exporter …）都必须继承此类并实现 export() 方法。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseExporter(ABC):
    """数据导出器的统一接口"""

    @abstractmethod
    def export(self, record: dict) -> None:
        """
        导出一条记录。

        Parameters
        ----------
        record : dict
            由 SmartCollar.generate_one_record() 产出的字典
        """

    @abstractmethod
    def flush(self) -> None:
        """强制刷盘 / 发送缓冲区中的所有数据"""

    @abstractmethod
    def close(self) -> None:
        """释放资源（关闭文件句柄 / 断开连接等）"""
