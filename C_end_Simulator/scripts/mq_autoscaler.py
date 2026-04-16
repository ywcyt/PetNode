"""MQ worker autoscaler for PetNode.

根据 RabbitMQ 队列积压量动态调整 docker compose 中 mq-worker 的副本数。

使用示例：
  python scripts/mq_autoscaler.py --compose-file C_end_Simulator/docker-compose.yml

核心策略：
- backlog = messages_ready + messages_unacknowledged
- target = ceil(backlog / target_messages_per_worker)
- target 会被限制在 [min_replicas, max_replicas]
- 通过 cooldown 避免短时间频繁扩缩
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, parse, request


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="根据 RabbitMQ 访问量自动扩缩 docker compose 服务",
    )
    parser.add_argument(
        "--compose-file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "docker-compose.yml",
        help="docker-compose.yml 路径",
    )
    parser.add_argument(
        "--service",
        default="mq-worker",
        help="需要扩缩容的 compose 服务名",
    )
    parser.add_argument(
        "--queue",
        default="petnode.records",
        help="RabbitMQ 队列名",
    )
    parser.add_argument(
        "--vhost",
        default="/",
        help="RabbitMQ vhost，默认 '/'",
    )
    parser.add_argument(
        "--rabbitmq-api-base",
        default="http://127.0.0.1:15672",
        help="RabbitMQ 管理 API 地址，例如 http://127.0.0.1:15672",
    )
    parser.add_argument(
        "--rabbitmq-user",
        default="guest",
        help="RabbitMQ 管理 API 用户名",
    )
    parser.add_argument(
        "--rabbitmq-pass",
        default="guest",
        help="RabbitMQ 管理 API 密码",
    )
    parser.add_argument(
        "--min-replicas",
        type=int,
        default=1,
        help="最小副本数",
    )
    parser.add_argument(
        "--max-replicas",
        type=int,
        default=6,
        help="最大副本数",
    )
    parser.add_argument(
        "--target-messages-per-worker",
        type=int,
        default=200,
        help="单个 worker 期望承载的队列消息数",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="轮询间隔（秒）",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=20.0,
        help="扩缩容冷却时间（秒）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印计划，不执行 docker compose 扩缩容",
    )
    args = parser.parse_args(argv)

    if args.min_replicas < 0:
        parser.error("--min-replicas 不能小于 0")
    if args.max_replicas < args.min_replicas:
        parser.error("--max-replicas 必须大于等于 --min-replicas")
    if args.target_messages_per_worker <= 0:
        parser.error("--target-messages-per-worker 必须大于 0")
    if args.poll_interval <= 0:
        parser.error("--poll-interval 必须大于 0")
    if args.cooldown < 0:
        parser.error("--cooldown 不能小于 0")

    return args


def _fetch_queue_depth(
    api_base: str,
    vhost: str,
    queue_name: str,
    username: str,
    password: str,
    timeout: float = 5.0,
) -> int:
    vhost_encoded = parse.quote(vhost, safe="")
    queue_encoded = parse.quote(queue_name, safe="")
    url = f"{api_base.rstrip('/')}/api/queues/{vhost_encoded}/{queue_encoded}"

    auth_plain = f"{username}:{password}".encode("utf-8")
    auth_value = base64.b64encode(auth_plain).decode("ascii")

    req = request.Request(url)
    req.add_header("Authorization", f"Basic {auth_value}")
    req.add_header("Accept", "application/json")

    with request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    ready = int(data.get("messages_ready", 0))
    unacked = int(data.get("messages_unacknowledged", 0))
    return ready + unacked


def _get_running_replicas(compose_file: Path, service: str) -> int:
    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "ps",
        service,
        "--status",
        "running",
        "-q",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "docker compose ps 执行失败")

    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return len(lines)


def _scale_service(compose_file: Path, service: str, replicas: int, dry_run: bool) -> None:
    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "up",
        "-d",
        "--no-recreate",
        "--scale",
        f"{service}={replicas}",
        service,
    ]

    printable = " ".join(cmd)
    if dry_run:
        print(f"[DRY-RUN] {printable}")
        return

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(err or "docker compose scale 执行失败")


def _calc_target(backlog: int, min_replicas: int, max_replicas: int, per_worker: int) -> int:
    ideal = int(math.ceil(backlog / per_worker)) if backlog > 0 else 0
    return max(min_replicas, min(max_replicas, ideal))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    compose_file = args.compose_file.resolve()

    if not compose_file.exists():
        print(f"[ERROR] compose 文件不存在: {compose_file}")
        return 2

    print(
        "[INFO] autoscaler 启动: "
        f"service={args.service}, queue={args.queue}, replicas={args.min_replicas}..{args.max_replicas}, "
        f"target_messages_per_worker={args.target_messages_per_worker}, cooldown={args.cooldown}s"
    )

    last_scale_ts = 0.0

    while True:
        try:
            backlog = _fetch_queue_depth(
                api_base=args.rabbitmq_api_base,
                vhost=args.vhost,
                queue_name=args.queue,
                username=args.rabbitmq_user,
                password=args.rabbitmq_pass,
            )

            current = _get_running_replicas(compose_file=compose_file, service=args.service)
            target = _calc_target(
                backlog=backlog,
                min_replicas=args.min_replicas,
                max_replicas=args.max_replicas,
                per_worker=args.target_messages_per_worker,
            )

            now = time.time()
            cooldown_left = max(0.0, args.cooldown - (now - last_scale_ts))

            print(
                "[METRIC] "
                f"backlog={backlog}, current={current}, target={target}, cooldown_left={cooldown_left:.1f}s"
            )

            if target != current:
                if cooldown_left > 0:
                    print("[SKIP] 冷却中，暂不扩缩容")
                else:
                    _scale_service(
                        compose_file=compose_file,
                        service=args.service,
                        replicas=target,
                        dry_run=args.dry_run,
                    )
                    last_scale_ts = now
                    print(f"[SCALE] {args.service}: {current} -> {target}")

        except KeyboardInterrupt:
            print("\n[INFO] autoscaler 已停止")
            return 0
        except (RuntimeError, error.URLError, ValueError, json.JSONDecodeError) as exc:
            # 拉取指标失败或 docker 命令失败时，仅记录并继续循环，避免守护进程退出。
            print(f"[WARN] 本轮处理失败: {exc}")

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    sys.exit(main())
