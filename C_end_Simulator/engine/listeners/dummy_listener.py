"""
DummyListener —— 假装在监听，控制台打印空转

当前阶段使用的占位 listener，不连接任何服务器。
每次 poll() 返回 None（无指令），并在日志中记录一次空转。
"""

from __future__ import annotations

import logging
from typing import Optional

from engine.listeners.base_listener import BaseListener

logger = logging.getLogger(__name__)


class DummyListener(BaseListener):
    """
    哑巴监听器：每次 poll() 返回 None，仅做日志打印。

    用于当前阶段（无远程服务器）的占位实现。
    """

    def __init__(self) -> None:
        self._closed = False

    def poll(self) -> Optional[dict]:
        """空转一次，返回 None"""
        if not self._closed:
            logger.debug("DummyListener: poll() — 无新指令（空转）")
        return None

    def close(self) -> None:
        """标记为已关闭"""
        if not self._closed:
            self._closed = True
            logger.debug("DummyListener: 已关闭")

    def __repr__(self) -> str:
        return "DummyListener()"