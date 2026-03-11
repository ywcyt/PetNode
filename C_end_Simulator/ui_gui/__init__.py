# ui_gui 包 —— 桌面图形界面（基于 PyQt6）
#
# 本模块是 PetNode 系统的 GUI 界面层，使用 PyQt6 实现桌面图形界面。
# 由于 PyQt6 依赖宿主机的图形环境（X11/Wayland），无法打包进 Docker 容器，
# 因此本模块仅在宿主机上运行，不参与 Docker 编排。
#
# 模块结构：
#   - app.py          : GUI 启动总入口，负责初始化 QApplication 和窗口切换
#   - login_window.py : 登录窗口类，处理用户登录逻辑
#   - main_window.py  : 主控制台窗口类，实时显示数据和发送控制指令
#
# 与 TUI (ui_tui/) 的关系：
#   - GUI 和 TUI 功能等价，都通过读写 output_data/ 目录与引擎通信
#   - GUI 适合在有图形环境的宿主机上使用
#   - TUI 适合在终端/Docker 环境中使用
#
# 当前状态：占位结构，具体实现待后续开发。
