"""
engine/main.py —— 核心调度器

职责：
  - 解析命令行参数（狗数量、Tick 数、间隔、种子等）
  - 创建 SmartCollar 实例 + FileExporter + DummyListener
  - 主循环：每隔 real_interval 秒调用项圈生成数据 → 导出到文件
  - 轮询 command.json 读取控制指令（stop/pause/resume/set_interval）
  - 优雅退出：Ctrl-C / SIGTERM

用法::

    python -m engine.main                          # 默认 1 只狗, 100 ticks
    python -m engine.main --dogs 3 --ticks 500     # 3 只狗, 500 ticks
    python -m engine.main --seed 42 --interval 2   # 可复现, 每 2 秒一轮
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Optional

from engine.models import DogProfile, SmartCollar
from engine.exporters import FileExporter
from engine.listeners import DummyListener

# ────────────────── 日志 ──────────────────

logger = logging.getLogger("engine")

# ────────────────── 常量 ──────────────────

_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output_data"
_COMMAND_FILE = "command.json"

# ────────────────── 指令读取 ──────────────────


def read_command(output_dir: Path) -> Optional[dict]:
    """
    从 command.json 读取控制指令。

    Parameters
    ----------
    output_dir : Path
        output_data 目录

    Returns
    -------
    dict | None
        解析后的指令字典；文件不存在或为空时返回 None。
    """
    cmd_path = output_dir / _COMMAND_FILE
    if not cmd_path.exists():
        return None
    try:
        text = cmd_path.read_text(encoding="utf-8").strip()
        if not text:
            return None
        return json.loads(text)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("读取 command.json 失败: %s", exc)
        return None


def write_engine_status(output_dir: Path, status: dict) -> None:
    """
    将引擎状态写入 engine_status.json。

    Parameters
    ----------
    output_dir : Path
        output_data 目录
    status : dict
        要写入的状态字典
    """
    status_path = output_dir / "engine_status.json"
    try:
        status_path.write_text(
            json.dumps(status, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("写入 engine_status.json 失败: %s", exc)


# ────────────────── 参数解析 ──────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    解析命令行参数。

    Parameters
    ----------
    argv : list[str] | None
        参数列表，默认读取 sys.argv
    """
    parser = argparse.ArgumentParser(
        description="PetNode C端 智能项圈数据模拟引擎",
    )
    parser.add_argument(
        "--dogs", type=int, default=1,
        help="模拟的狗数量（默认 1）",
    )
    parser.add_argument(
        "--ticks", type=int, default=100,
        help="每只狗生成的 tick 总数（默认 100）",
    )
    parser.add_argument(
        "--tick-minutes", type=int, default=1,
        help="每个 tick 对应的模拟时间（分钟，默认 1）",
    )
    parser.add_argument(
        "--interval", type=float, default=0.0,
        help="每轮 tick 之间的真实等待秒数（默认 0，即尽快跑完）",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="随机种子（用于可复现模拟）",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="输出目录（默认 output_data/）",
    )
    parser.add_argument(
        "--log-level", type=str, default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认 INFO）",
    )
    return parser.parse_args(argv)


# ────────────────── 核心调度 ──────────────────


def run(
    num_dogs: int = 1,
    num_ticks: int = 100,
    tick_minutes: int = 1,
    real_interval: float = 0.0,
    seed: int | None = None,
    output_dir: str | Path | None = None,
) -> list[dict]:
    """
    运行模拟引擎主循环。

    Parameters
    ----------
    num_dogs : int
        狗的数量
    num_ticks : int
        每只狗生成的 tick 数量
    tick_minutes : int
        每 tick 对应的模拟分钟数
    real_interval : float
        每轮 tick 之间的真实间隔秒数（0 表示尽快跑完）
    seed : int | None
        随机种子
    output_dir : str | Path | None
        输出目录

    Returns
    -------
    list[dict]
        所有生成的记录列表（方便测试/调试）
    """
    out_path = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR
    out_path.mkdir(parents=True, exist_ok=True)

    # ── 创建项圈 ──
    collars: list[SmartCollar] = []
    for i in range(num_dogs):
        dog_seed = (seed + i) if seed is not None else None
        collar = SmartCollar(
            tick_interval=timedelta(minutes=tick_minutes),
            seed=dog_seed,
        )
        collars.append(collar)
        logger.info("项圈 #%d 已创建: %s", i + 1, collar.profile)

    # ── 创建 exporter ──
    exporter = FileExporter(output_dir=out_path)
    logger.info("FileExporter 已就绪: %s", exporter.filepath)

    # ── 创建 listener ──
    listener = DummyListener()
    logger.info("DummyListener 已注册")

    # ── 写入初始引擎状态 ──
    write_engine_status(out_path, {
        "running": True,
        "num_dogs": num_dogs,
        "total_ticks": num_ticks,
        "tick_minutes": tick_minutes,
        "current_tick": 0,
    })

    # ── 优雅退出标志 ──
    stopped = False

    def _signal_handler(signum: int, frame: object) -> None:
        nonlocal stopped
        logger.info("收到信号 %d，准备停止…", signum)
        stopped = True

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # ── 主循环 ──
    all_records: list[dict] = []
    paused = False

    try:
        for tick in range(num_ticks):
            if stopped:
                logger.info("引擎被中断，已完成 %d/%d ticks", tick, num_ticks)
                break

            # 轮询 command.json
            cmd = read_command(out_path)
            if cmd is not None:
                action = cmd.get("action")
                if action == "stop":
                    logger.info("收到 stop 指令，停止模拟")
                    stopped = True
                    break
                elif action == "pause":
                    paused = True
                    logger.info("收到 pause 指令，暂停模拟")
                elif action == "resume":
                    paused = False
                    logger.info("收到 resume 指令，恢复模拟")
                elif action == "set_interval":
                    new_interval = cmd.get("value")
                    if isinstance(new_interval, (int, float)) and new_interval >= 0:
                        real_interval = float(new_interval)
                        logger.info("实时间隔已更新为 %.2f 秒", real_interval)

            # 暂停状态下跳过生成
            if paused:
                if real_interval > 0:
                    time.sleep(real_interval)
                continue

            # 轮询 listener
            listener.poll()

            # 生成数据并导出
            for collar in collars:
                record = collar.generate_one_record()
                exporter.export(record)
                all_records.append(record)

            # 定期 flush（每 10 ticks 或最后一个 tick）
            if (tick + 1) % 10 == 0 or tick == num_ticks - 1:
                exporter.flush()

            # 更新引擎状态
            if (tick + 1) % 50 == 0 or tick == num_ticks - 1:
                write_engine_status(out_path, {
                    "running": True,
                    "num_dogs": num_dogs,
                    "total_ticks": num_ticks,
                    "tick_minutes": tick_minutes,
                    "current_tick": tick + 1,
                })

            # 日志
            if (tick + 1) % 50 == 0:
                logger.info(
                    "进度: %d/%d ticks 完成 (%d 条记录)",
                    tick + 1, num_ticks, len(all_records),
                )

            # 真实间隔等待
            if real_interval > 0:
                time.sleep(real_interval)

    finally:
        # ── 清理 ──
        exporter.flush()
        exporter.close()
        listener.close()
        write_engine_status(out_path, {
            "running": False,
            "num_dogs": num_dogs,
            "total_ticks": num_ticks,
            "tick_minutes": tick_minutes,
            "current_tick": len(all_records) // max(num_dogs, 1),
        })
        logger.info(
            "引擎已停止。共生成 %d 条记录，已写入 %s",
            len(all_records), exporter.filepath,
        )

    return all_records


# ────────────────── 入口 ──────────────────


def main(argv: list[str] | None = None) -> None:
    """CLI 入口"""
    args = parse_args(argv)

    # 配置日志
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info("PetNode 引擎启动")
    logger.info(
        "参数: dogs=%d, ticks=%d, tick_minutes=%d, interval=%.2f, seed=%s",
        args.dogs, args.ticks, args.tick_minutes, args.interval, args.seed,
    )

    run(
        num_dogs=args.dogs,
        num_ticks=args.ticks,
        tick_minutes=args.tick_minutes,
        real_interval=args.interval,
        seed=args.seed,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
