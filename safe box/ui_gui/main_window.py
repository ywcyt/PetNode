"""
ui_gui/main_window.py —— GUI 主控制台窗口类（占位）

本文件为占位文件，待后续实现 PyQt6 主控制台界面。

预期功能：
  - 使用 PyQt6 QWidget 构建主控制台界面
  - 定时读取 output_data/realtime_stream.jsonl 并刷新数据表
  - 定时读取 output_data/engine_status.json 并显示引擎状态
  - 提供控制按钮：暂停/恢复/停止引擎、调整 tick 间隔
  - 通过写入 output_data/command.json 向引擎发送指令
  - 支持图表展示（如心率趋势图、步数统计图等）

与 TUI 监控大屏 (ui_tui/screens/dashboard_screen.py) 功能等价，
只是用 PyQt6 图形控件和图表库替代了 Textual 终端表格和日志控件。
"""
