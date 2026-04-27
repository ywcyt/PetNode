"""
command_api.py —— TUI 后端指令发送接口

职责：
  - 向 command.json 写入控制指令
  - 引擎通过轮询 command.json 读取并执行指令
  - 支持的指令：stop / pause / resume / set_interval

TUI 前端通过调用此接口发送指令，无需直接操作 command.json 文件。

用法::

    api = CommandAPI(output_dir="/app/output_data")
    api.send_stop()                  # 停止引擎
    api.send_pause()                 # 暂停引擎
    api.send_resume()                # 恢复引擎
    api.send_set_interval(2.0)       # 设置 tick 间隔为 2 秒
    api.clear_command()              # 清空指令文件
"""

from __future__ import annotations

import json
from pathlib import Path


# 默认输出目录
_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output_data"
# 指令文件名
_COMMAND_FILE = "command.json"


class CommandAPI:
    """
    TUI 后端指令发送接口。

    Parameters
    ----------
    output_dir : str | Path | None
        output_data 目录路径
    """

    def __init__(self, output_dir: str | Path | None = None) -> None:
        self._output_dir = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR

    def _write_command(self, cmd: dict) -> None:
        """
        将指令字典写入 command.json。

        Parameters
        ----------
        cmd : dict
            指令字典，至少包含 ``action`` 字段
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        cmd_path = self._output_dir / _COMMAND_FILE
        cmd_path.write_text(
            json.dumps(cmd, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def send_stop(self) -> None:
        """发送 stop 指令，停止引擎模拟"""
        self._write_command({"action": "stop"})

    def send_pause(self) -> None:
        """发送 pause 指令，暂停引擎模拟"""
        self._write_command({"action": "pause"})

    def send_resume(self) -> None:
        """发送 resume 指令，恢复引擎模拟"""
        self._write_command({"action": "resume"})

    def send_set_interval(self, interval: float) -> None:
        """
        发送 set_interval 指令，调整 tick 间隔。

        Parameters
        ----------
        interval : float
            新的 tick 间隔（秒），必须 >= 0
        """
        if interval < 0:
            raise ValueError("interval 必须 >= 0")
        self._write_command({"action": "set_interval", "value": interval})

    def clear_command(self) -> None:
        """
        清空 command.json（写入空对象）。

        用于指令被引擎读取后的清理操作。
        """
        cmd_path = self._output_dir / _COMMAND_FILE
        if cmd_path.exists():
            cmd_path.write_text("", encoding="utf-8")

    def get_current_command(self) -> dict | None:
        """
        读取当前 command.json 的内容。

        Returns
        -------
        dict | None
            当前指令字典；文件为空或不存在时返回 None
        """
        cmd_path = self._output_dir / _COMMAND_FILE
        if not cmd_path.exists():
            return None
        try:
            text = cmd_path.read_text(encoding="utf-8").strip()
            if not text:
                return None
            return json.loads(text)
        except (json.JSONDecodeError, OSError):
            return None

    def __repr__(self) -> str:
        return f"CommandAPI(output_dir={self._output_dir})"
