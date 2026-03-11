"""
WsListener —— 🔮 未来阶段占位：通过 WebSocket 接收服务器下发的控制指令

本文件当前为空壳，留作未来阶段实现。

预期功能：
  - 继承 BaseListener，实现 poll() / close()
  - 通过 WebSocket 长连接与 S端（远程服务器）保持通信
  - 接收服务器下发的控制指令（如 start / stop / set_interval 等）
  - 将收到的指令以 dict 形式返回给调度器 (main.py)

与 DummyListener 的关系：
  - DummyListener 是"假装在监听"的占位实现（当前阶段正在使用）
  - WsListener 是"真正通过 WebSocket 监听远程服务器"的实现（未来替换）
  - 两者都继承自 BaseListener，调度器通过统一接口调用（策略模式）

使用方式（未来实现后）::

    listener = WsListener(ws_url="wss://server.example.com/ws/control")
    cmd = listener.poll()     # 检查是否有新指令
    if cmd:
        print(cmd)            # → {"action": "set_interval", "value": 5}
    listener.close()          # 断开 WebSocket 连接
"""
