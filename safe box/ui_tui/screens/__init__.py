"""
ui_tui.screens —— TUI 屏幕模块

包含：
  - LoginScreen    : 终端登录屏
  - DashboardScreen: 实时数据监控大屏
"""

from ui_tui.screens.login_screen import LoginScreen
from ui_tui.screens.dashboard_screen import DashboardScreen

__all__ = ["LoginScreen", "DashboardScreen"]