"""flask_server.mq_worker —— RabbitMQ 队列消费者（Worker）

职责：
- 从 RabbitMQ durable queue 消费 Engine 发送的 record 消息。
- 在“消息层”完成身份验证与防篡改验签：
  - Authorization: Bearer <api_key>
  - X-Signature : HMAC-SHA256(record_json_bytes)
- 验证通过后，调用 storage.save(record) 落库（默认 MongoStorage）。
- 成功：basic_ack
- 失败：
  - 鉴权/验签失败：basic_reject(requeue=False)（拒绝毒消息，避免无限重试）
  - 暂时性错误（Mongo 不可用/网络抖动等）：basic_nack(requeue=True) 让 RabbitMQ 重投递（重传机制）

为什么要独立 Worker？
- flask-server 用 gunicorn 多 worker 会产生多个进程；
  如果把消费逻辑塞进 Flask 进程里，容易出现“多进程重复消费/竞争”。
- 独立 mq-worker 是更清晰、更可控的生产实践。

环境变量：
- RABBITMQ_URL   : amqp://guest:guest@rabbitmq:5672/
- RABBITMQ_QUEUE : petnode.records
- API_KEY / HMAC_KEY : 与 Engine 一致
- STORAGE_BACKEND / MONGO_* : 复用 Flask 存储选择逻辑（默认 mongo）

运行方式（docker-compose 已配置）：
- docker compose up -d rabbitmq mongodb mq-worker
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sys
import time

import pika

# storage 选择与 app.py 保持一致
try:
    from flask_server.storage.file_storage import FileStorage
    from flask_server.storage.mongo_storage import MongoStorage
except Exception:
    from .storage.file_storage import FileStorage
    from .storage.mongo_storage import MongoStorage


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mq_worker")


def _build_storage():
    """与 flask_server.app.py 同逻辑：根据 STORAGE_BACKEND 选择存储实现。"""
    backend = os.environ.get("STORAGE_BACKEND", "mongo").strip().lower()
    data_dir = os.environ.get("DATA_DIR", "/app/data")

    if backend == "file":
        logger.info("mq-worker 使用 FileStorage: dir=%s", data_dir)
        return FileStorage(data_dir=data_dir)

    logger.info(
        "mq-worker 使用 MongoStorage: uri=%s db=%s collection=%s",
        os.environ.get("MONGO_URI", "mongodb://mongodb:27017"),
        os.environ.get("MONGO_DB", "petnode"),
        os.environ.get("MONGO_COLLECTION", "received_records"),
    )
    return MongoStorage()


def _expected_api_key() -> str:
    return os.environ.get("API_KEY", "petnode_secret_key_2026")


def _hmac_key() -> str:
    return os.environ.get("HMAC_KEY", "petnode_hmac_secret_2026")


def _verify_auth_and_signature(body: bytes, headers: dict | None) -> tuple[bool, str]:
    """返回 (ok, reason)。"""
    headers = headers or {}

    auth = headers.get("Authorization") or headers.get("authorization")
    if not auth or not isinstance(auth, str) or not auth.startswith("Bearer "):
        return False, "missing/invalid Authorization"

    token = auth[len("Bearer "):]
    if token != _expected_api_key():
        return False, "api key mismatch"

    incoming_sig = headers.get("X-Signature") or headers.get("x-signature")
    if not incoming_sig or not isinstance(incoming_sig, str):
        return False, "missing X-Signature"

    expected_sig = hmac.new(
        _hmac_key().encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(incoming_sig, expected_sig):
        return False, "signature mismatch"

    return True, "ok"


def main() -> int:
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
    queue_name = os.environ.get("RABBITMQ_QUEUE", "petnode.records")

    # 连接循环：RabbitMQ 重启/网络抖动时可自动重连
    while True:
        storage = None
        connection = None
        try:
            storage = _build_storage()
            params = pika.URLParameters(rabbitmq_url)
            connection = pika.BlockingConnection(params)
            channel = connection.channel()

            channel.queue_declare(queue=queue_name, durable=True)
            channel.basic_qos(prefetch_count=50)

            logger.info("mq-worker 已连接 RabbitMQ，开始消费: queue=%s", queue_name)

            def on_message(ch, method, properties, body: bytes):
                # 1) 鉴权 + 验签
                ok, reason = _verify_auth_and_signature(body, getattr(properties, "headers", None))
                if not ok:
                    logger.warning("丢弃消息（鉴权/验签失败）: %s", reason)
                    # 毒消息直接拒绝，不重回队列
                    ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
                    return

                # 2) 解析 JSON
                try:
                    record = json.loads(body.decode("utf-8"))
                    if not isinstance(record, dict):
                        raise ValueError("record must be a JSON object")
                except Exception as exc:
                    logger.warning("丢弃消息（JSON 解析失败）: %s", exc)
                    ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
                    return

                # 3) 入库
                try:
                    storage.save(record)
                except Exception as exc:
                    # 暂时性失败：让消息回队列，等待下次重投递（重传）
                    logger.error("入库失败，将 NACK 并重试: %s", exc)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                    return

                # 4) ACK
                ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_consume(queue=queue_name, on_message_callback=on_message, auto_ack=False)
            channel.start_consuming()

        except KeyboardInterrupt:
            logger.info("收到 Ctrl-C，mq-worker 退出")
            try:
                if storage is not None:
                    storage.close()
            except Exception:
                logger.debug("关闭 storage 失败", exc_info=True)
            try:
                if connection is not None and connection.is_open:
                    connection.close()
            except Exception:
                logger.debug("关闭 RabbitMQ connection 失败", exc_info=True)
            return 0

        except Exception as exc:
            # 连接/消费异常：等待后重连
            logger.error("mq-worker 异常，将重连: %s", exc)
            try:
                if storage is not None:
                    storage.close()
            except Exception:
                logger.debug("关闭 storage 失败", exc_info=True)
            try:
                if connection is not None and connection.is_open:
                    connection.close()
            except Exception:
                logger.debug("关闭 RabbitMQ connection 失败", exc_info=True)
            time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
