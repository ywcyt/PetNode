"""
dashboard_screen.py —— PetNodeOS 实时数据监控大屏

职责：
  - 显示引擎运行状态（运行/暂停/停止）
  - 实时展示各只狗的最新数据（心率、呼吸、体温、步数、行为等）
  - 提供引擎控制功能（暂停/恢复/停止/调整间隔）
  - 定时自动刷新数据

界面分离原则：
  - 此文件只负责界面渲染和用户交互
  - 所有数据读取通过 backend.DataAPI 接口
  - 所有指令发送通过 backend.CommandAPI 接口
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.screen import Screen
from textual.widgets import (
    Static,
    Button,
    Footer,
    Header,
    DataTable,
    Input,
    Log,
)
from textual.timer import Timer


# ────────────────── 顶部状态栏 ──────────────────

_BANNER = (
    "[bold cyan]╔══════════════════════════════════════╗[/bold cyan]\n"
    "[bold cyan]║[/bold cyan]   🐾 [bold]PetNodeOS[/bold]  [dim]Dashboard[/dim]   "
    "       [bold cyan]║[/bold cyan]\n"
    "[bold cyan]╚══════════════════════════════════════╝[/bold cyan]"
)


class DashboardScreen(Screen):
    """
    PetNodeOS 实时数据监控大屏。

    功能：
      - 顶部状态栏：显示用户信息和引擎状态
      - 中间数据表：展示每只狗的最新数据
      - 底部控制区：暂停/恢复/停止/调整间隔等操作
      - 实时日志区：显示操作日志
    """

    CSS = """
    DashboardScreen {
        background: $surface;
    }

    #dashboard-container {
        width: 100%;
        height: 100%;
        padding: 0 1;
    }

    #top-banner {
        text-align: center;
        height: 3;
        margin-bottom: 1;
    }

    #status-bar {
        height: 3;
        border: round $primary;
        padding: 0 2;
        margin-bottom: 1;
    }

    #user-info {
        width: 1fr;
    }

    #engine-status {
        width: 1fr;
        text-align: center;
    }

    #data-stats {
        width: 1fr;
        text-align: right;
    }

    #data-table {
        height: 1fr;
        min-height: 8;
        border: round $accent;
        margin-bottom: 1;
    }

    #controls-section {
        height: 3;
        margin-bottom: 1;
    }

    .ctrl-btn {
        margin-right: 1;
    }

    #interval-input {
        width: 16;
        margin-left: 1;
    }

    #log-section {
        height: 8;
        border: round $warning;
    }

    #log-title {
        height: 1;
        padding: 0 1;
        color: $warning;
    }
    """

    BINDINGS = [
        ("p", "toggle_pause", "暂停/恢复"),
        ("s", "stop_engine", "停止引擎"),
        ("r", "refresh_data", "刷新数据"),
        ("l", "logout", "登出"),
        ("escape", "quit", "退出"),
    ]

    # 刷新间隔（秒）
    _REFRESH_INTERVAL = 2.0

    def __init__(
        self,
        user_id: str = "",
        num_dogs: int = 1,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._user_id = user_id
        self._num_dogs = num_dogs
        self._paused = False
        self._refresh_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Vertical(id="dashboard-container"):
            yield Static(_BANNER, id="top-banner")

            # 状态栏
            with Horizontal(id="status-bar"):
                yield Static(
                    f"👤 [bold]{self._user_id}[/bold]  🐕 ×{self._num_dogs}",
                    id="user-info",
                )
                yield Static(
                    "🔄 [bold green]等待引擎...[/bold green]",
                    id="engine-status",
                )
                yield Static(
                    "📊 记录: 0",
                    id="data-stats",
                )

            # 数据表
            yield DataTable(id="data-table")

            # 控制区
            with Horizontal(id="controls-section"):
                yield Button(
                    "⏸ 暂停 Pause", variant="warning",
                    id="pause-btn", classes="ctrl-btn",
                )
                yield Button(
                    "▶ 恢复 Resume", variant="success",
                    id="resume-btn", classes="ctrl-btn",
                )
                yield Button(
                    "⏹ 停止 Stop", variant="error",
                    id="stop-btn", classes="ctrl-btn",
                )
                yield Button(
                    "🔄 刷新 Refresh", variant="primary",
                    id="refresh-btn", classes="ctrl-btn",
                )
                yield Static(" ⏱ 间隔(s):", id="interval-label")
                yield Input(
                    placeholder="秒",
                    value="1.0",
                    id="interval-input",
                )
                yield Button(
                    "✓", variant="default",
                    id="set-interval-btn", classes="ctrl-btn",
                )

            # 日志区
            with Vertical(id="log-section"):
                yield Static(
                    "📝 操作日志 Operation Log", id="log-title",
                )
                yield Log(id="op-log", auto_scroll=True)

        yield Footer()

    def on_mount(self) -> None:
        """屏幕挂载时初始化数据表并启动定时刷新"""
        # 初始化数据表列
        table = self.query_one("#data-table", DataTable)
        table.add_columns(
            "🐕 设备ID",
            "⏰ 时间",
            "🏃 行为",
            "❤️ 心率",
            "🌬 呼吸",
            "🌡 体温",
            "👣 步数",
            "🗺 GPS",
            "🏥 事件",
        )

        # 记录日志
        log = self.query_one("#op-log", Log)
        log.write_line(f"[系统] 用户 {self._user_id} 已登录，管理 {self._num_dogs} 只狗")
        log.write_line(f"[系统] 数据刷新间隔: {self._REFRESH_INTERVAL}s")

        # 启动定时刷新
        self._refresh_timer = self.set_interval(
            self._REFRESH_INTERVAL, self._refresh_all,
        )

        # 首次刷新
        self._refresh_all()

    def _refresh_all(self) -> None:
        """刷新所有数据（状态 + 数据表）"""
        self._refresh_engine_status()
        self._refresh_data_table()

    def _refresh_engine_status(self) -> None:
        """从后端读取并更新引擎状态显示"""
        data_api = self.app.data_api  # type: ignore[attr-defined]
        status = data_api.get_engine_status()

        status_widget = self.query_one("#engine-status", Static)
        stats_widget = self.query_one("#data-stats", Static)

        if status is None:
            status_widget.update("⏳ [bold yellow]引擎未启动[/bold yellow]")
            return

        running = status.get("running", False)
        current_tick = status.get("current_tick", 0)
        total_ticks = status.get("total_ticks", 0)
        num_dogs = status.get("num_dogs", 0)

        if running:
            progress = (
                f"{current_tick}/{total_ticks}" if total_ticks > 0
                else str(current_tick)
            )
            status_widget.update(
                f"🟢 [bold green]运行中[/bold green]  "
                f"Tick: {progress}  🐕 ×{num_dogs}"
            )
        else:
            status_widget.update(
                f"🔴 [bold red]已停止[/bold red]  "
                f"Tick: {current_tick}/{total_ticks}"
            )

        # 更新记录统计
        total_records = data_api.get_total_record_count()
        stats_widget.update(f"📊 记录: {total_records}")

    def _refresh_data_table(self) -> None:
        """从后端读取数据并更新数据表"""
        data_api = self.app.data_api  # type: ignore[attr-defined]
        records = data_api.get_latest_records(self._num_dogs * 3)

        table = self.query_one("#data-table", DataTable)
        table.clear()

        if not records:
            return

        # 按设备分组，只显示每个设备的最新一条
        latest_by_device: dict[str, dict] = {}
        for record in records:
            device_id = record.get("device_id", "?")
            if device_id not in latest_by_device:
                latest_by_device[device_id] = record

        for device_id, record in latest_by_device.items():
            # 格式化时间戳（只取时间部分）
            ts = record.get("timestamp", "")
            if "T" in ts:
                ts = ts.split("T")[1][:8]

            behavior = record.get("behavior", "?")
            behavior_icon = {
                "sleeping": "😴 sleeping",
                "resting": "🛋 resting",
                "walking": "🚶 walking",
                "running": "🏃 running",
            }.get(behavior, behavior)

            hr = record.get("heart_rate", 0)
            rr = record.get("resp_rate", 0)
            temp = record.get("temperature", 0)
            steps = record.get("steps", 0)
            lat = record.get("gps_lat", 0)
            lng = record.get("gps_lng", 0)
            event = record.get("event") or "—"
            phase = record.get("event_phase") or ""
            event_display = f"{event}" if event == "—" else f"⚠ {event}({phase})"

            # 心率颜色标记
            hr_display = f"{hr}"
            if hr > 160:
                hr_display = f"[red]{hr}[/red]"
            elif hr < 50:
                hr_display = f"[blue]{hr}[/blue]"

            # 体温颜色标记
            temp_display = f"{temp}°C"
            if temp > 39.5:
                temp_display = f"[red]{temp}°C[/red]"

            table.add_row(
                device_id[:12],
                ts,
                behavior_icon,
                hr_display,
                str(rr),
                temp_display,
                str(steps),
                f"{lat:.4f},{lng:.4f}",
                event_display,
            )

    # ────────────────── 按钮事件 ──────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """处理控制按钮点击"""
        cmd_api = self.app.command_api  # type: ignore[attr-defined]
        log = self.query_one("#op-log", Log)

        if event.button.id == "pause-btn":
            cmd_api.send_pause()
            self._paused = True
            log.write_line("[指令] ⏸ 已发送暂停指令")

        elif event.button.id == "resume-btn":
            cmd_api.send_resume()
            self._paused = False
            log.write_line("[指令] ▶ 已发送恢复指令")

        elif event.button.id == "stop-btn":
            cmd_api.send_stop()
            log.write_line("[指令] ⏹ 已发送停止指令")

        elif event.button.id == "refresh-btn":
            self._refresh_all()
            log.write_line("[操作] 🔄 手动刷新数据")

        elif event.button.id == "set-interval-btn":
            self._set_interval()

    def _set_interval(self) -> None:
        """设置 tick 间隔"""
        cmd_api = self.app.command_api  # type: ignore[attr-defined]
        log = self.query_one("#op-log", Log)
        interval_input = self.query_one("#interval-input", Input)

        try:
            interval = float(interval_input.value)
            cmd_api.send_set_interval(interval)
            log.write_line(f"[指令] ⏱ 已设置间隔为 {interval}s")
        except ValueError:
            log.write_line("[错误] ⚠ 无效的间隔值")

    # ────────────────── 快捷键 ──────────────────

    def action_toggle_pause(self) -> None:
        """切换暂停/恢复"""
        cmd_api = self.app.command_api  # type: ignore[attr-defined]
        log = self.query_one("#op-log", Log)

        if self._paused:
            cmd_api.send_resume()
            self._paused = False
            log.write_line("[指令] ▶ 恢复引擎")
        else:
            cmd_api.send_pause()
            self._paused = True
            log.write_line("[指令] ⏸ 暂停引擎")

    def action_stop_engine(self) -> None:
        """停止引擎"""
        cmd_api = self.app.command_api  # type: ignore[attr-defined]
        log = self.query_one("#op-log", Log)
        cmd_api.send_stop()
        log.write_line("[指令] ⏹ 停止引擎")

    def action_refresh_data(self) -> None:
        """手动刷新"""
        self._refresh_all()
        log = self.query_one("#op-log", Log)
        log.write_line("[操作] 🔄 手动刷新")

    def action_logout(self) -> None:
        """登出回到登录页"""
        user_store = self.app.user_store  # type: ignore[attr-defined]
        user_store.logout()
        self.app.switch_to_login()  # type: ignore[attr-defined]

    def action_quit(self) -> None:
        """退出应用"""
        self.app.exit()