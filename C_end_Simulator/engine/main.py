"""engine/main.py —— 核心调度器

职责：
- 解析命令行参数（设备分组数、狗数量、Tick 数、间隔、种子等）
- 创建 SmartCollar 实例 + 主通道 Exporter + FileExporter(TUI 缓冲) + DummyListener
- 主循环：每个 tick 生成数据 → 走“主通道”上报/入队 → 写本地缓冲文件
- 支持多线程：每个 tick 内，使用线程池并行生成每只狗的数据
- 轮询 command.json 读取控制指令（stop/pause/resume/set_interval）
- 优雅退出：Ctrl-C / SIGTERM

主通道（可切换）：
- http：HttpExporter → HTTP POST 到 Flask /api/data（由 Flask 负责鉴权/验签与入库）
- mq ：MqExporter   → RabbitMQ queue（由 mq-worker 消费：鉴权/验签 → MongoStorage 入库）

数据流向（概览）：
    record
        ├─ 主通道：HttpExporter 或 MqExporter
        │     └─ 失败（断网/不可达）→ output_data/offline_cache/（flush() 自动补发后删除）
        └─ TUI 缓冲：FileExporter → realtime_stream.jsonl（滚动截断，最多 500 行）

用法::

        # 1) 默认走 HTTP
        python -m engine.main

        # 2) 显式选择走 MQ
        python -m engine.main --export-backend mq

        # 3) 通过环境变量选择
        EXPORT_BACKEND=mq python -m engine.main
"""
#
# ┌─ 你的服务器 47.109.200.132（pppetnode.com）─────────────────────┐
# │                                                              │
# │  ┌──────────────────┐                                        │
# │  │  Flask 容器 (云端) │ ← 监听 0.0.0.0:5000                    │
# │  │  petnode-flask    │                                       │
# │  └────────▲─────────┘                                        │
# │           │                                                  │
# │           │ HTTP POST http://pppetnode.com:5000/api/data     │
# │           │ （走公网域名解析，模拟真实网络通信）                    │
# │           │                                                  │
# │  ┌────────┴───┬───────────┬───────────┬── ... ──┐            │
# │  │ engine-1   │ engine-2  │ engine-3  │  engine-10│          │
# │  │ (客户端1)   │ (客户端2)  │ (客户端3)  │ (客户端10)│           │
# │  └────────────┴───────────┴───────────┴──────────┘           │
# │                                                              │
# └──────────────────────────────────────────────────────────────┘
#          ▲
#          │  你的电脑也能连：
#          │  API_URL=http://pppetnode.com:5000/api/data
#          │  python -m engine.main --dogs 2
# ┌────────┴──────────┐
# │   你的电脑（本地）  │
# └───────────────────┘
#

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path
from typing import Optional
import os

from engine.models import DogProfile, SmartCollar
from engine.exporters import FileExporter, HttpExporter, MqExporter
from engine.listeners import DummyListener

# ────────────────── 日志 ──────────────────

# 统一使用 "engine" 命名空间的日志器
logger = logging.getLogger("engine")

# ────────────────── 常量 ──────────────────

# 默认输出目录：C_end_Simulator/output_data/
_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output_data"
# 控制指令文件名（TUI/GUI 写指令 → Engine 读指令）
_COMMAND_FILE = "command.json"
# TUI 缓冲文件最大保留行数（超出后滚动截断，只保留最新的）
_BUFFER_MAX_LINES = 500

# ────────────────── 工具函数 ──────────────────


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


def _truncate_buffer(filepath: Path, keep_lines: int = _BUFFER_MAX_LINES) -> None:
    """
    截断 TUI 缓冲文件，只保留最后 keep_lines 行。

    防止 realtime_stream.jsonl 无限增长——
    历史数据已经通过 HttpExporter 发到 Flask 永久保存了，
    本地文件只需要保留最近的数据给 TUI 实时显示。

    Parameters
    ----------
    filepath : Path
        要截断的文件路径（realtime_stream.jsonl）
    keep_lines : int
        保留的最大行数（默认 500）
    """
    try:
        # 文件不存在，跳过
        if not filepath.exists():
            return

        # 读取所有行
        lines = filepath.read_text(encoding="utf-8").splitlines()

        # 行数未超限，不需要截断
        if len(lines) <= keep_lines:
            return

        # 只保留最后 keep_lines 行（最新的数据）
        recent = lines[-keep_lines:]

        # 重写文件（覆盖模式，丢弃旧数据）
        filepath.write_text(
            "\n".join(recent) + "\n",
            encoding="utf-8",
        )

        logger.debug(
            "TUI 缓冲文件已截断: %s (%d → %d 行)",
            filepath.name, len(lines), keep_lines,
        )
    except OSError as exc:
        logger.warning("截断缓冲文件失败: %s", exc)


# ────────────────── 参数解析 ──────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    解析命令行参数。

    Parameters
    ----------
    argv : list[str] | None
        参数列表，默认读取 sys.argv

    支持的参数：
      --groups        设备分组数量（默认 1，仅用于运行元数据）
      --dogs          模拟的狗数量（默认 1）
      --ticks         每只狗生成的 tick 总数（默认 100）
      --tick-minutes  每个 tick 对应的模拟时间分钟数（默认 1）
      --interval      每轮 tick 之间的真实等待秒数（默认 0，即尽快跑完）
      --seed          随机种子（用于可复现模拟）
      --output-dir    输出目录（默认 output_data/）
      --api-url       Flask 服务器 API 地址（默认 http://pppetnode.com:5000/api/data ）
      --log-level     日志级别（默认 INFO）
    """
    parser = argparse.ArgumentParser(
        description="PetNode C端 智能项圈数据模拟引擎",
    )
    parser.add_argument(
        "--groups", "--users", dest="groups", type=int, default=1,
        help="设备分组数量（默认 1，仅用于运行元数据；兼容旧参数 --users）",
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
        "--api-url", type=str,
        default=os.environ.get("API_URL", "http://flask-server:5000/api/data"),
        help="Flask 服务器 API 地址（优先读环境变量 API_URL）",
    ) # 47.109.200.132
    parser.add_argument(
        "--export-backend", type=str,
        default=os.environ.get("EXPORT_BACKEND", "http"),
        choices=["http", "mq"],
        help=(
            "主通道导出后端：http 或 mq（优先读环境变量 EXPORT_BACKEND；默认 http）。"
            "mq 表示发送到 RabbitMQ，由 mq-worker 消费并入库。"
        ),
    )
    parser.add_argument(
        "--api-key", type=str,
        default=os.environ.get("API_KEY", "petnode_secret_key_2026"),
        help="API Key，用于 Flask 服务器鉴权（优先读环境变量 API_KEY）",
    )
    parser.add_argument(
        "--hmac-key", type=str,
        default=os.environ.get("HMAC_KEY", "petnode_hmac_secret_2026"),
        help="HMAC 密钥，用于请求体防篡改签名（优先读环境变量 HMAC_KEY）",
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
    num_groups: int = 1,
    # api_url: str = "http://172.28.69.242:5000/api/data",
    api_url: str = os.environ.get("API_URL", "http://flask-server:5000/api/data"),
    api_key: str | None = None,
    hmac_key: str | None = None,
    export_backend: str | None = None,
    num_users: int | None = None,
) -> list[dict]:
    """
    运行模拟引擎主循环（支持多线程并行生成数据）。

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
    num_groups : int
        设备分组数量，仅用于运行状态元数据，不参与 record 身份建模
    api_url : str
        Flask 服务器 API 地址（HttpExporter 的目标）
    api_key : str | None
        API Key，用于 Flask 服务器鉴权（None 时自动从环境变量 API_KEY 读取）
    hmac_key : str | None
        HMAC 密钥，用于请求体防篡改签名（None 时自动从环境变量 HMAC_KEY 读取）
    export_backend : str | None
        主通道导出后端："http" 或 "mq"。
        - http: 使用 HttpExporter 直接 POST 到 Flask /api/data
        - mq  : 使用 MqExporter 发布到 RabbitMQ 队列，由 mq-worker 消费写库
    num_users : int | None
        已废弃的兼容参数；如传入则映射到 num_groups

    Returns
    -------
    list[dict]
        所有生成的记录列表（方便测试/调试）
    """
    if num_users is not None:
        num_groups = num_users

    out_path = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR
    out_path.mkdir(parents=True, exist_ok=True)


    # ── 创建项圈（SmartCollar 实例）──
    # 每只狗使用 (seed + i) 作为随机种子，确保不同狗有不同的随机序列但整体可复现
    # record 身份只由 device_id 表达；num_groups 仅用于状态展示等元数据
    collars: list[SmartCollar] = []
    for i in range(num_dogs):
        dog_seed = (seed + i) if seed is not None else None
        collar = SmartCollar(
            tick_interval=timedelta(minutes=tick_minutes),
            seed=dog_seed,
        )
        collars.append(collar)

    # ── 创建 exporters（数据导出器）──

    # 主通道：根据 export_backend 选择 HTTP 或 MQ。
    #
    # 选择建议：
    # - 需要“解耦 + 队列重投递 + worker 异步入库”时用 mq
    # - 需要“最少组件、直接打 API”时用 http
    chosen_backend = (export_backend or os.environ.get("EXPORT_BACKEND", "http")).strip().lower()

    if chosen_backend == "mq":
        main_exporter = MqExporter(api_key=api_key, hmac_key=hmac_key)
        logger.info("MqExporter 已就绪 (主通道): queue=%s", main_exporter.queue_name)
    else:
        main_exporter = HttpExporter(api_url=api_url, api_key=api_key, hmac_key=hmac_key)
        logger.info("HttpExporter 已就绪 (主通道): %s", main_exporter.api_url)

    # TUI 缓冲：FileExporter — 写本地文件给 TUI 实时读取（滚动截断，不永久保存）
    file_exporter = FileExporter(output_dir=out_path)
    logger.info("FileExporter 已就绪 (TUI缓冲): %s", file_exporter.filepath)

    # ── 创建 listener（指令监听器）──
    # 当前阶段使用 DummyListener，不连接任何远程服务器
    listener = DummyListener()
    logger.info("DummyListener 已注册")

    # ── 写入初始引擎状态 ──
    # engine_status.json 让 TUI/GUI 知道引擎的运行状态
    write_engine_status(out_path, {
        "running": True,
        "num_groups": num_groups,
        "num_dogs": num_dogs,
        "total_ticks": num_ticks,
        "tick_minutes": tick_minutes,
        "current_tick": 0,
    })

    # ── 优雅退出标志 ──
    # 收到 SIGINT (Ctrl-C) 或 SIGTERM 时设置 stopped=True，主循环检测后优雅退出
    stopped = False

    def _signal_handler(signum: int, frame: object) -> None:
        nonlocal stopped
        logger.info("收到信号 %d，准备停止…", signum)
        stopped = True

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # ── 主循环 ──
    # 每个 tick：轮询指令 → 生成数据 → 发 HTTP + 写缓冲 → 等待间隔
    all_records: list[dict] = []
    paused = False

    try:
        # 使用线程池并行生成数据——每个 tick 内，各只狗的记录在独立线程中并行生成
        max_workers = min(num_dogs, os.cpu_count() or 4)
        max_workers = max(max_workers, 1)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for tick in range(num_ticks):
                if stopped:
                    logger.info("引擎被中断，已完成 %d/%d ticks", tick, num_ticks)
                    break

                # 轮询 command.json 读取控制指令（stop/pause/resume/set_interval）
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
                        # 动态调整每轮 tick 之间的真实等待时间
                        new_interval = cmd.get("value")
                        if isinstance(new_interval, (int, float)) and new_interval >= 0:
                            real_interval = float(new_interval)
                            logger.info("实时间隔已更新为 %.2f 秒", real_interval)

                # 暂停状态下跳过数据生成，但仍保持等待循环
                if paused:
                    if real_interval > 0:
                        time.sleep(real_interval)
                    continue

                # 轮询 listener（当前阶段为空操作）
                listener.poll()

                # 使用多线程并行为每只狗生成数据并导出
                # 每只狗在独立线程中调用 generate_one_record()
                futures = [
                    executor.submit(collar.generate_one_record)
                    for collar in collars
                ]
                # 收集各线程生成的记录（as_completed 在主线程中顺序回收结果）
                for future in as_completed(futures):
                    record = future.result()
                    # 主通道：HTTP 或 MQ（失败则自动缓存到 offline_cache/）
                    main_exporter.export(record)
                    # TUI 缓冲：写本地文件（给 TUI 实时读取显示）
                    file_exporter.export(record)
                    all_records.append(record)

                # 定期 flush（每 10 ticks 或最后一个 tick）
                if (tick + 1) % 10 == 0 or tick == num_ticks - 1:
                    main_exporter.flush()            # 补发离线缓存（如果有的话）
                    file_exporter.flush()            # TUI 缓冲刷盘

                # 定期截断 TUI 缓冲文件（每 100 ticks），防止无限膨胀
                if (tick + 1) % 100 == 0:
                    _truncate_buffer(file_exporter.filepath)

                # 定期更新引擎状态文件（每 50 ticks 或最后一个 tick）
                if (tick + 1) % 50 == 0 or tick == num_ticks - 1:
                    write_engine_status(out_path, {
                        "running": True,
                        "num_groups": num_groups,
                        "num_dogs": num_dogs,
                        "total_ticks": num_ticks,
                        "tick_minutes": tick_minutes,
                        "current_tick": tick + 1,
                    })

                # 进度日志（每 50 ticks 打印一次）
                if (tick + 1) % 50 == 0:
                    logger.info(
                        "进度: %d/%d ticks 完成 (%d 条记录)",
                        tick + 1, num_ticks, len(all_records),
                    )

                # 真实间隔等待（interval=0 表示尽快跑完，不等待）
                if real_interval > 0:
                    time.sleep(real_interval)

    finally:
        # ── 清理：无论正常结束还是异常退出，都确保资源被释放 ──
        main_exporter.flush()                        # 最后一次补发离线缓存
        main_exporter.close()                        # 关闭连接/资源
        file_exporter.flush()                        # TUI 缓冲刷盘
        file_exporter.close()                        # 关闭文件句柄
        listener.close()
        # 写入最终引擎状态（running=False）
        write_engine_status(out_path, {
            "running": False,
            "num_groups": num_groups,
            "num_dogs": num_dogs,
            "total_ticks": num_ticks,
            "tick_minutes": tick_minutes,
            "current_tick": len(all_records) // max(num_dogs, 1),
        })
        logger.info(
            "引擎已停止。共生成 %d 条记录, 主通道发送=%s, TUI 缓冲=%s",
            len(all_records), main_exporter, file_exporter.filepath,
        )

    return all_records


# ────────────────── 入口 ──────────────────


def main(argv: list[str] | None = None) -> None:
    """
    CLI 入口——解析命令行参数并启动模拟引擎。

    典型用法：
        python -m engine.main                                   # 默认 1 分组 1 只狗, 100 ticks
        python -m engine.main --groups 2 --dogs 6 --ticks 500   # 2 分组 6 只狗, 500 ticks
        python -m engine.main --seed 42 --interval 2           # 可复现, 每 2 秒一轮
    """
    args = parse_args(argv)

    # 配置日志格式和级别
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info("PetNode 引擎启动")
    logger.info(
        "参数: groups=%d, dogs=%d, ticks=%d, tick_minutes=%d, interval=%.2f, seed=%s, api=%s",
        args.groups, args.dogs, args.ticks, args.tick_minutes,
        args.interval, args.seed, args.api_url,
    )

    # 调用核心调度函数
    run(
        num_dogs=args.dogs,
        num_ticks=args.ticks,
        tick_minutes=args.tick_minutes,
        real_interval=args.interval,
        seed=args.seed,
        output_dir=args.output_dir,
        num_groups=args.groups,
        api_url=args.api_url,                        # ← 🆕 传入 Flask API 地址
        api_key=args.api_key,                        # ← 🆕 传入 API Key
        hmac_key=args.hmac_key,                      # ← 🆕 传入 HMAC 密钥
        export_backend=args.export_backend,
    )


if __name__ == "__main__":
    main()
