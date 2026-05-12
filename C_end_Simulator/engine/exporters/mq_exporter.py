"""engine.exporters.mq_exporter —— RabbitMQ 消息队列导出器

本导出器用于“任务二：构建消息队列 / 任务三：身份验证与重传机制”。

目标：
- Engine 端作为 producer，把每条 record 发送到 RabbitMQ 的 durable queue。
- 消费者（flask_server.mq_worker）从队列取出消息，做鉴权/验签后落库。

可靠性与重传：
- 发布时使用 durable queue + persistent message（delivery_mode=2）。
- 开启 publisher confirms（confirm_delivery）以确认消息真正被 broker 接收。
- 若网络断开/发布失败：将 record 缓存到 output_data/offline_cache/，
  后续 flush() 会自动补发并在成功后删除缓存文件（与 HttpExporter 一致）。

身份验证与防篡改：
- 通过消息 headers 携带：
  - Authorization: Bearer <api_key>
  - X-Signature : HMAC-SHA256(record_json_bytes)
- HMAC 使用 sort_keys=True 的 JSON 规范化，确保 producer/consumer 计算一致。

环境变量：
- RABBITMQ_URL   : amqp://guest:guest@rabbitmq:5672/
- RABBITMQ_QUEUE : petnode.records
- API_KEY / HMAC_KEY : 与 HTTP 通道保持一致

依赖：
- pika（RabbitMQ Python client）
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

import pika

from engine.exporters.base_exporter import BaseExporter

logger = logging.getLogger("engine.exporters.mq")

def _default_rabbitmq_url() -> str:
    return os.environ.get("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")


def _default_queue() -> str:
    return os.environ.get("RABBITMQ_QUEUE", "petnode.records")

_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "output_data" / "offline_cache"

# 每次 flush() 最多补发多少条缓存记录，避免恢复后瞬间打爆 broker/worker
_MAX_RETRY_PER_FLUSH = 100


class MqExporter(BaseExporter):
    """RabbitMQ 导出器（producer）。"""

    def __init__(
        self,
        rabbitmq_url: str | None = None,
        queue_name: str | None = None,
        cache_dir: str | Path | None = None,
        api_key: str | None = None,
        hmac_key: str | None = None,
    ) -> None:
        self._url = rabbitmq_url or _default_rabbitmq_url()
        self._queue = queue_name or _default_queue()

        self._cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # 鉴权配置：默认与 HTTP 通道一致
        self._api_key = api_key or os.environ.get("API_KEY", "petnode_secret_key_2026")
        self._hmac_key = hmac_key or os.environ.get("HMAC_KEY", "petnode_hmac_secret_2026")

        # 连接对象延迟创建（首次 publish 时连接）
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None

        self._lock = threading.Lock()

        self._sent_count = 0
        self._cached_count = 0
        self._retry_count = 0

        logger.info("MqExporter 已就绪: url=%s queue=%s cache=%s", self._url, self._queue, self._cache_dir)

    # ────────────────── BaseExporter 接口 ──────────────────

    def export(self, record: dict) -> None:
        """发布一条 record；失败则缓存到离线文件。"""
        try:
            self._publish_record(record)
            self._sent_count += 1
            if self._sent_count % 200 == 0:
                logger.info("MQ 已发布 %d 条记录", self._sent_count)
        except (TypeError, ValueError) as exc:
            logger.error("记录序列化失败（跳过）: %s", exc)
        except Exception as exc:
            logger.warning("MQ 发布失败（将缓存到本地）: %s", exc)
            self._cache_record(record)

    def flush(self) -> None:
        """补发离线缓存目录中的记录（部分成功时重写文件避免重复发送）。"""
        cache_files = sorted(self._cache_dir.glob("cache_*.jsonl"))
        if not cache_files:
            return

        logger.info("开始补发离线缓存（MQ）: %d 个文件", len(cache_files))
        retried = 0

        for cache_file in cache_files:
            if retried >= _MAX_RETRY_PER_FLUSH:
                logger.info("本次补发已达上限 (%d)，剩余下次处理", _MAX_RETRY_PER_FLUSH)
                break

            try:
                lines = cache_file.read_text(encoding="utf-8").splitlines()
                remaining: list[str] = []
                file_done = True

                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        continue

                    if retried >= _MAX_RETRY_PER_FLUSH:
                        file_done = False
                        remaining.append(stripped)
                        continue

                    try:
                        record = json.loads(stripped)
                    except json.JSONDecodeError:
                        logger.warning("跳过损坏的缓存行: %s", stripped[:80])
                        continue

                    try:
                        self._publish_record(record)
                        retried += 1
                        self._retry_count += 1
                    except Exception:
                        file_done = False
                        remaining.append(stripped)
                        break  # MQ 不可达，剩余行稍后重试

                if file_done and not remaining:
                    cache_file.unlink()
                    logger.info("缓存文件已补发并删除: %s", cache_file.name)
                elif remaining:
                    cache_file.write_text("\n".join(remaining) + "\n", encoding="utf-8")
                    logger.warning("部分补发完成，%d 条保留在缓存中", len(remaining))
                    break

            except OSError as exc:
                logger.error("读取缓存文件失败: %s, 错误: %s", cache_file.name, exc)
                continue

        if retried > 0:
            logger.info("本次补发完成（MQ）: 成功 %d 条, 累计补发 %d 条", retried, self._retry_count)

    def close(self) -> None:
        """释放 MQ 连接。"""
        try:
            if self._channel is not None and self._channel.is_open:
                self._channel.close()
        except Exception:
            logger.debug("关闭 MQ channel 失败", exc_info=True)

        try:
            if self._connection is not None and self._connection.is_open:
                self._connection.close()
        except Exception:
            logger.debug("关闭 MQ connection 失败", exc_info=True)

        logger.info(
            "MqExporter 已关闭: 发布=%d, 缓存=%d, 补发=%d",
            self._sent_count,
            self._cached_count,
            self._retry_count,
        )

    # ────────────────── 内部方法 ──────────────────

    def _ensure_connected(self) -> None:
        """确保连接与 channel 可用（不可用则重建）。"""
        if self._connection is not None and self._connection.is_open and self._channel is not None and self._channel.is_open:
            return

        # 连接参数：直接使用 URLParameters
        params = pika.URLParameters(self._url)
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()

        # durable queue（幂等）
        self._channel.queue_declare(queue=self._queue, durable=True)

        # publisher confirms：让 basic_publish 返回确认结果
        self._channel.confirm_delivery()

    def _publish_record(self, record: dict) -> None:
        if not isinstance(record, dict):
            raise TypeError("record must be a dict")

        body_bytes = json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")

        sig = hmac.new(
            self._hmac_key.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Signature": sig,
        }

        props = pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,  # 2 = persistent
            headers=headers,
        )

        # 多线程生成数据时，export() 可能并发调用；
        # BlockingConnection/channel 不是线程安全的，因此需要锁。
        with self._lock:
            self._ensure_connected()
            assert self._channel is not None

            ok = self._channel.basic_publish(
                exchange="",
                routing_key=self._queue,
                body=body_bytes,
                properties=props,
                mandatory=True,
            )

            # 在 pika 不同版本/模式下，basic_publish 可能返回 True 或 None。
            # 失败场景通常以异常（例如 UnroutableError / NackError）体现。
            if ok is False:
                raise RuntimeError("RabbitMQ publish not confirmed")

    def _cache_record(self, record: dict) -> None:
        ts = record.get("timestamp", "unknown")
        date_str = ts[:10] if isinstance(ts, str) and len(ts) >= 10 else "unknown"
        cache_file = self._cache_dir / f"cache_{date_str}.jsonl"
        line = json.dumps(record, ensure_ascii=False)

        with self._lock:
            with open(cache_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())

        self._cached_count += 1
        if self._cached_count % 10 == 0:
            logger.warning("已缓存 %d 条数据到 %s", self._cached_count, self._cache_dir)

    # ────────────────── 便利属性 ──────────────────

    @property
    def rabbitmq_url(self) -> str:
        return self._url

    @property
    def queue_name(self) -> str:
        return self._queue

    def __repr__(self) -> str:
        return (
            f"MqExporter(url={self._url}, queue={self._queue}, "
            f"sent={self._sent_count}, cached={self._cached_count}, retried={self._retry_count})"
        )
