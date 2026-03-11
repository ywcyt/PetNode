"""
BaseListener —— 指令接收层的抽象基类

所有 listener（dummy_listener, ws_listener …）都必须继承此类并实现 poll() 方法。
Listener 负责轮询/监听外部控制指令，并返回给调度器。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class BaseListener(ABC):
    """指令监听器的统一接口"""

    @abstractmethod
    def poll(self) -> Optional[dict]:
        """
        轮询一次，返回最新指令（如果有）。

        Returns
        -------
        dict | None
            指令字典，没有新指令时返回 None。
            典型字段: {"action": "start" | "stop" | "set_interval", ...}
        """

    @abstractmethod
    def close(self) -> None:
        """释放资源（关闭连接等）"""