"""
ui_tui/app.py —— PetNodeOS 终端界面启动入口

职责：
  - 初始化 Textual App
  - 注入后端 API 实例（DataAPI, CommandAPI, UserStore）
  - 管理屏幕切换（登录 → 仪表盘）

架构分离：
  - app.py 作为 TUI 层的"胶水"，将后端 API 注入到各屏幕中
  - 各屏幕通过 self.app.data_api / self.app.command_api / self.app.user_store 访问后端
  - 后端 API 层封装了所有文件 I/O 和数据解析逻辑

用法::

    # 直接运行
    python -m ui_tui.app

    # 指定数据目录
    python -m ui_tui.app --output-dir /app/output_data

    # Docker 中运行
    docker compose run --rm tui
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from textual.app import App

from ui_tui.backend import DataAPI, CommandAPI, UserStore
from ui_tui.screens import LoginScreen, DashboardScreen


class PetNodeApp(App):
    """
    PetNodeOS 终端界面应用。

    持有后端 API 实例，供各屏幕使用：
      - data_api    : 读取引擎状态和实时数据
      - command_api : 发送引擎控制指令
      - user_store  : 用户登录与会话管理
    """

    TITLE = "PetNodeOS"
    SUB_TITLE = "🐾 智能宠物项圈数据模拟系统"
    CSS = """
    Screen {
        background: $surface;
    }
    """

    def __init__(self, output_dir: str | Path | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.data_api = DataAPI(output_dir=output_dir)
        self.command_api = CommandAPI(output_dir=output_dir)
        self.user_store = UserStore(output_dir=output_dir)

    def on_mount(self) -> None:
        """应用启动时显示登录屏幕"""
        self.push_screen(LoginScreen())

    def switch_to_dashboard(self, user_id: str, num_dogs: int) -> None:
        """
        切换到仪表盘屏幕。

        Parameters
        ----------
        user_id : str
            已登录用户的 ID
        num_dogs : int
            用户拥有的狗数量
        """
        self.switch_screen(DashboardScreen(user_id=user_id, num_dogs=num_dogs))

    def switch_to_login(self) -> None:
        """切换回登录屏幕"""
        self.switch_screen(LoginScreen())


# ────────────────── CLI 入口 ──────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="PetNodeOS TUI — 终端界面监控系统",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="output_data 目录路径（默认自动检测）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """TUI 入口函数"""
    args = parse_args(argv)
    app = PetNodeApp(output_dir=args.output_dir)
    app.run()


if __name__ == "__main__":
    main()