"""
ui_gui/app.py —— GUI 启动总入口（占位）

本文件为占位文件，待后续实现 PyQt6 桌面图形界面。

预期功能：
  - 初始化 PyQt6 QApplication
  - 创建并管理登录窗口 (LoginWindow) 和主控制台窗口 (MainWindow) 的切换
  - 与 ui_tui/app.py 功能等价：注入后端 API，管理界面生命周期

预期使用方式::

    # 直接运行
    python -m ui_gui.app

    # 或
    cd C_end_Simulator
    python ui_gui/app.py

注意：
  - 需要安装 PyQt6（见 ui_gui/requirements.txt）
  - 需要宿主机有图形环境（X11/Wayland），无法在 Docker 容器中运行
"""
