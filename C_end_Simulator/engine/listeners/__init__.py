# engine/listeners 包 —— 指令接收层（监听服务器下发的控制指令）
# BaseListener 定义了统一的监听接口（poll / close）；
# DummyListener 是当前阶段使用的占位实现，每次 poll() 返回 None（不连接任何远程服务器）；
# ws_listener 是未来阶段的占位，用于通过 WebSocket 接收服务器下发的控制指令。

from .base_listener import BaseListener
from .dummy_listener import DummyListener

__all__ = ["BaseListener", "DummyListener"]