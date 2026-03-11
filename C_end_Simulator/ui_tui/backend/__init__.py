"""
ui_tui.backend —— TUI 后端接口层

职责：
  - 将 TUI 界面与底层数据存储/引擎控制解耦
  - 提供统一的 API 供 TUI 前端调用
  - 所有文件 I/O 和数据解析逻辑集中在此层

模块：
  - data_api    : 读取引擎状态和实时数据流
  - command_api : 向引擎发送控制指令
  - user_store  : 用户登录与会话管理
"""

from ui_tui.backend.data_api import DataAPI
from ui_tui.backend.command_api import CommandAPI
from ui_tui.backend.user_store import UserStore

__all__ = ["DataAPI", "CommandAPI", "UserStore"]
