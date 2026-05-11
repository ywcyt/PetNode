"""
login_screen.py —— PetNodeOS 终端登录屏

职责：
  - 显示 PetNodeOS 品牌 ASCII Art 标题
  - 让用户输入用户名和狗的数量
  - 调用 UserStore.login() 进行登录
  - 登录成功后切换到 Dashboard 屏幕

界面分离原则：
  - 此文件只负责界面渲染和用户交互
  - 所有数据逻辑通过 backend.UserStore 接口完成
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Center, Vertical, Container
from textual.screen import Screen
from textual.widgets import Static, Input, Button, Footer


# ────────────────── PetNodeOS ASCII Art ──────────────────

_LOGO = r"""[bold cyan]
  ╔═══════════════════════════════════════════════════════════╗
  ║                                                           ║
  ║   ██████╗ ███████╗████████╗███╗   ██╗ ██████╗ ██████╗     ║
  ║   ██╔══██╗██╔════╝╚══██╔══╝████╗  ██║██╔═══██╗██╔══██╗   ║
  ║   ██████╔╝█████╗     ██║   ██╔██╗ ██║██║   ██║██║  ██║   ║
  ║   ██╔═══╝ ██╔══╝     ██║   ██║╚██╗██║██║   ██║██║  ██║   ║
  ║   ██║     ███████╗   ██║   ██║ ╚████║╚██████╔╝██████╔╝   ║
  ║   ╚═╝     ╚══════╝   ╚═╝   ╚═╝  ╚═══╝ ╚═════╝ ╚═════╝   ║
  ║                         [bold green]O S[/bold green]                              ║
  ║                                                           ║
  ╚═══════════════════════════════════════════════════════════╝
[/bold cyan]"""

_SUBTITLE = "[dim]🐾 智能宠物项圈数据模拟系统  ·  Smart Pet Collar Simulator[/dim]"

_DOG_ART = r"""[yellow]
      / \__
     (    @\___
      /         O
     /   (_____/
    /_____/   U[/yellow]"""


class LoginScreen(Screen):
    """
    PetNodeOS 登录屏幕。

    用户输入用户名和狗数量后，调用后端 UserStore 进行登录。
    登录成功后通过 app 切换到 DashboardScreen。
    """

    CSS = """
    LoginScreen {
        background: $surface;
    }

    #login-container {
        width: 70;
        height: auto;
        margin: 1 0;
        padding: 1 2;
    }

    #logo {
        text-align: center;
        margin-bottom: 0;
    }

    #subtitle {
        text-align: center;
        margin-bottom: 1;
    }

    #dog-art {
        text-align: center;
        margin-bottom: 1;
    }

    #login-box {
        width: 60;
        height: auto;
        border: round $primary;
        padding: 1 2;
        margin: 0 5;
    }

    #login-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: $text;
    }

    .login-label {
        margin-top: 1;
        margin-bottom: 0;
        color: $text-muted;
    }

    #username-input {
        margin-bottom: 1;
    }

    #dogs-input {
        margin-bottom: 1;
    }

    #login-btn {
        width: 100%;
        margin-top: 1;
    }

    #error-msg {
        text-align: center;
        color: $error;
        margin-top: 1;
        height: 1;
    }

    #version-info {
        text-align: center;
        color: $text-disabled;
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "quit", "退出"),
    ]

    def compose(self) -> ComposeResult:
        with Center():
            with Vertical(id="login-container"):
                yield Static(_LOGO, id="logo")
                yield Static(_SUBTITLE, id="subtitle")
                yield Static(_DOG_ART, id="dog-art")

                with Container(id="login-box"):
                    yield Static(
                        "🔐 [bold]系统登录  System Login[/bold]",
                        id="login-title",
                    )
                    yield Static("👤 用户名 Username", classes="login-label")
                    yield Input(
                        placeholder="请输入用户名...",
                        id="username-input",
                    )
                    yield Static("🐕 狗数量 Number of Dogs", classes="login-label")
                    yield Input(
                        placeholder="请输入狗的数量 (1-10)...",
                        value="1",
                        id="dogs-input",
                    )
                    yield Button(
                        "▶ 登录  Login",
                        variant="primary",
                        id="login-btn",
                    )
                    yield Static("", id="error-msg")

                yield Static(
                    "[dim]PetNodeOS v1.0  ·  C端智能项圈模拟器[/dim]",
                    id="version-info",
                )

        yield Footer()

    def on_mount(self) -> None:
        """屏幕挂载时，聚焦到用户名输入框"""
        self.query_one("#username-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """处理登录按钮点击"""
        if event.button.id == "login-btn":
            self._do_login()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """处理输入框回车事件"""
        if event.input.id == "username-input":
            self.query_one("#dogs-input", Input).focus()
        elif event.input.id == "dogs-input":
            self._do_login()

    def _do_login(self) -> None:
        """执行登录逻辑"""
        error_widget = self.query_one("#error-msg", Static)

        username = self.query_one("#username-input", Input).value.strip()
        dogs_str = self.query_one("#dogs-input", Input).value.strip()

        if not username:
            error_widget.update("[bold red]⚠ 请输入用户名！[/bold red]")
            return

        try:
            num_dogs = int(dogs_str)
            if num_dogs < 1 or num_dogs > 10:
                error_widget.update("[bold red]⚠ 狗数量须在 1-10 之间！[/bold red]")
                return
        except ValueError:
            error_widget.update("[bold red]⚠ 请输入有效的数字！[/bold red]")
            return

        try:
            user_store = self.app.user_store  # type: ignore[attr-defined]
            user_id = user_store.login(username, num_dogs)
            error_widget.update(
                f"[bold green]✓ 登录成功！UID: {user_id} | 🐕 ×{num_dogs}[/bold green]"
            )
            self.app.switch_to_dashboard(user_id, num_dogs)  # type: ignore[attr-defined]
        except ValueError as exc:
            error_widget.update(f"[bold red]⚠ {exc}[/bold red]")

    def action_quit(self) -> None:
        """退出应用"""
        self.app.exit()