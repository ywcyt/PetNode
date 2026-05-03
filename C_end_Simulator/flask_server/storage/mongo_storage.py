"""
MongoStorage —— 将接收到的数据保存到 MongoDB

为什么需要它？
- FileStorage 把数据写到 JSONL 文件，适合早期阶段/离线分析；

设计原则：
- 仍然遵循 BaseStorage 接口（策略模式）：app.py 只调用 save()/close()，不关心底层。
- 默认读取环境变量配置，便于 docker-compose 注入。
- 初始化时主动 ping MongoDB，尽早暴露配置或网络问题（fail fast）。

环境变量（docker-compose 推荐）：
- MONGO_URI         : Mongo 连接串，例如 mongodb://mongodb:27017
- MONGO_DB          : 数据库名，默认 petnode
- MONGO_COLLECTION  : 集合名，默认 received_records

注意：
- 本实现对写入做“最小加工”：额外加一个 ingested_at（服务器接收时间，UTC）。
- 原始 record 会原样入库，字段保持与 Engine POST 的 JSON 一致。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from pymongo import MongoClient
from pymongo.collection import Collection

from .base_storage import BaseStorage

logger = logging.getLogger("storage.mongo")


class MongoStorage(BaseStorage):
    """MongoDB 存储实现。

    线程安全说明：
    - PyMongo 的 MongoClient 是线程安全的，建议全局复用。
    - Flask 在 gunicorn 多 worker 模式下，每个 worker 是独立进程：
      每个进程各自创建一个 MongoClient 是合理的。

    Parameters
    ----------
    mongo_uri : str | None
        MongoDB 连接串（优先使用参数，其次环境变量 MONGO_URI）。
    db_name : str | None
        数据库名（优先参数，其次环境变量 MONGO_DB）。
    collection_name : str | None
        集合名（优先参数，其次环境变量 MONGO_COLLECTION）。
    """

    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        db_name: Optional[str] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        # ── 读取配置（参数优先，其次环境变量，最后给默认值）──
        self.mongo_uri = mongo_uri or os.environ.get("MONGO_URI", "mongodb://mongodb:27017")
        self.db_name = db_name or os.environ.get("MONGO_DB", "petnode")
        self.collection_name = collection_name or os.environ.get("MONGO_COLLECTION", "received_records")

        # 连接超时设置（毫秒）：让容器启动失败更快显性化，避免卡死
        server_selection_timeout_ms = int(os.environ.get("MONGO_SERVER_SELECTION_TIMEOUT_MS", "2000"))
        connect_timeout_ms = int(os.environ.get("MONGO_CONNECT_TIMEOUT_MS", "2000"))

        # ── 创建 MongoClient（不会立刻连接，直到第一次操作/或 ping）──
        self._client = MongoClient(
            self.mongo_uri,
            serverSelectionTimeoutMS=server_selection_timeout_ms,
            connectTimeoutMS=connect_timeout_ms,
        )

        # ── 主动 ping 一下 MongoDB：fail fast ──
        # 如果 Mongo 容器没起来、DNS 不通、端口不通，这里会直接抛异常。
        self._client.admin.command("ping")

        # 获取集合句柄
        self._collection: Collection = self._client[self.db_name][self.collection_name]

        # ── 可选：创建常用索引 ──
        # create_index 是幂等的：已存在同名索引不会重复创建。
        # 这些索引能提升按 user/device/时间的查询性能。
        try:
            self._collection.create_index([("device_id", 1), ("timestamp", 1)])
        except Exception:
            # 索引创建失败不应阻塞主流程（例如权限受限），只记录日志
            logger.warning("MongoStorage 创建索引失败（将继续运行）", exc_info=True)

        logger.info(
            "MongoStorage initialized: uri=%s db=%s collection=%s",
            self.mongo_uri,
            self.db_name,
            self.collection_name,
        )

    def save(self, record: dict) -> None:
        """保存一条数据记录到 MongoDB。

        Raises
        ------
        Exception
            PyMongo 写入失败会抛异常，由 app.py 捕获并返回 500。
        """
        if not isinstance(record, dict):
            raise TypeError("record must be a dict")

        # 为避免上层复用同一个 dict 导致潜在副作用，这里复制一份
        doc = dict(record)

        # 额外补充服务器接收时间（UTC）
        doc["ingested_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"

        # 插入一条文档
        self._collection.insert_one(doc)

    def query_records(
        self,
        user_id: Optional[str] = None,
        device_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """按用户、设备和时间范围查询实时记录。"""
        criteria: dict[str, object] = {}

        if user_id:
            criteria["user_id"] = user_id
        if device_id:
            criteria["device_id"] = device_id
        if start_time or end_time:
            timestamp_filter: dict[str, object] = {}
            if start_time:
                timestamp_filter["$gte"] = start_time.isoformat()
            if end_time:
                timestamp_filter["$lte"] = end_time.isoformat()
            criteria["timestamp"] = timestamp_filter

        cursor = (
            self._collection.find(criteria, {"_id": 0})
            .sort("timestamp", -1)
            .skip(max(offset, 0))
            .limit(max(limit, 1))
        )
        return [dict(document) for document in cursor]

    def close(self) -> None:
        """关闭 MongoClient 连接。"""
        self._client.close()
