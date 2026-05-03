"""
db.py —— 轻量 MongoDB 连接助手（供 vx API Blueprint 使用）

与 MongoStorage 的区别：
  - MongoStorage 是数据写入存储层，用于 Engine 上报数据。
  - get_db() / ensure_indexes() 是 vx API 层的读查询入口，
    以懒加载方式复用相同的 MongoDB 连接，不重复创建连接池。

使用方式：
    from flask_server.db import get_db

    db = get_db()
    record = db["received_records"].find_one({"device_id": "xxx"})
"""

from __future__ import annotations

import logging
import os

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

logger = logging.getLogger("flask_server.db")

# 懒加载单例 MongoClient
_client: MongoClient | None = None


def get_client() -> MongoClient:
    """返回全局 MongoClient 单例（懒加载）。"""
    global _client
    if _client is None:
        uri = os.environ.get("MONGO_URI", "mongodb://mongodb:27017")
        _client = MongoClient(uri)
    return _client


def get_db():
    """返回 petnode 数据库句柄。"""
    db_name = os.environ.get("MONGO_DB", "petnode")
    return get_client()[db_name]


def ensure_indexes() -> None:
    """为 vx API 所需集合创建必要索引（幂等操作）。

    失败时只记录警告，不阻断服务启动。
    """
    db = get_db()
    try:
        # wechat_bindings: openid 唯一索引；unionid 稀疏唯一索引
        db["wechat_bindings"].create_index(
            [("openid", ASCENDING)],
            unique=True,
            name="idx_openid_unique",
        )
        db["wechat_bindings"].create_index(
            [("unionid", ASCENDING)],
            unique=True,
            sparse=True,
            name="idx_unionid_unique",
        )
        db["wechat_bindings"].create_index(
            [("user_id", ASCENDING)],
            name="idx_binding_user_id",
        )

        # user_pets: (user_id, device_id) 复合唯一索引
        db["user_pets"].create_index(
            [("user_id", ASCENDING), ("device_id", ASCENDING)],
            unique=True,
            name="idx_user_pet",
        )

        # received_records: (device_id, timestamp desc) 覆盖最新记录查询
        db["received_records"].create_index(
            [("device_id", ASCENDING), ("timestamp", DESCENDING)],
            name="idx_device_ts_desc",
        )

        logger.info("vx API MongoDB indexes ensured")
    except PyMongoError as exc:
        logger.warning("ensure_indexes failed (will continue): %s", exc)
