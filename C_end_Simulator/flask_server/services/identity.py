"""
services/identity.py —— 用户身份规范化与哈希工具

提供：
  normalize_identity(raw_name)         → 规范化标识字符串（trim + lower）
  build_user_hash(user_id, secret)     → 基于 HMAC-SHA256 的稳定匿名哈希
  get_or_create_user_hash(db, user_id) → 查库 / 生成 / 落库（幂等）

设计说明：
  - 哈希值用于对外匿名标识，内部始终保留真实 user_id。
  - HMAC 密钥从环境变量 HASH_SECRET 读取（默认值仅用于开发/测试）。
  - get_or_create_user_hash 写入 users 集合的 user_hash 字段，保证全局唯一且稳定。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

logger = logging.getLogger("flask_server.services.identity")

_HASH_SECRET_FALLBACK = "petnode_hash_secret_2026"


def _hash_secret() -> str:
    return os.environ.get("HASH_SECRET", _HASH_SECRET_FALLBACK)


# ────────────────────────────────────────────────
# 公开内部函数
# ────────────────────────────────────────────────


def normalize_identity(raw_name: str) -> str:
    """规范化用户标识字符串。

    将原始标识进行 strip + lower，确保同一来源的不同大小写写法
    能够映射到相同的规范形式，从而得到相同的哈希输入。

    Parameters
    ----------
    raw_name : str
        原始标识（用户名、邮箱或其他字符串）。

    Returns
    -------
    str
        规范化后的字符串。

    Raises
    ------
    ValueError
        raw_name 为空或全为空白字符时抛出。
    """
    if not raw_name or not raw_name.strip():
        raise ValueError("raw_name 不能为空")
    return raw_name.strip().lower()


def build_user_hash(user_id: str, secret: str | None = None) -> str:
    """生成用户的稳定匿名哈希标识。

    使用 HMAC-SHA256(secret, user_id) 算法，截取前 24 位十六进制字符，
    保证：
      - 相同 user_id + secret → 相同哈希（稳定性）
      - 不同 user_id → 不同哈希（唯一性）
      - 无法从哈希反推 user_id（单向性）

    Parameters
    ----------
    user_id : str
        系统内部用户 ID（UUID 字符串）。
    secret : str | None
        HMAC 签名密钥；为 None 时从环境变量 HASH_SECRET 读取。

    Returns
    -------
    str
        24 字符的十六进制哈希前缀，如 ``"a3f2c1d4e5b6a7f8c9d0e1f2"``。

    Raises
    ------
    ValueError
        user_id 为空时抛出。
    RuntimeError
        secret 为空时抛出（防止无密钥哈希）。
    """
    if not user_id:
        raise ValueError("user_id 不能为空")
    key = secret if secret is not None else _hash_secret()
    if not key:
        raise RuntimeError("HASH_SECRET 未配置，拒绝生成哈希")
    digest = hmac.new(
        key.encode("utf-8"),
        user_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:24]


def get_or_create_user_hash(db, user_id: str) -> str:
    """查询或创建用户的匿名哈希标识（幂等）。

    优先从 users 集合的 user_hash 字段读取；若不存在则生成并写入，
    保证每个 user_id 只对应一个固定的 user_hash。

    Parameters
    ----------
    db
        MongoDB 数据库句柄（由 flask_server.db.get_db() 提供）。
    user_id : str
        系统用户 ID。

    Returns
    -------
    str
        该用户的 user_hash（24 字符十六进制字符串）。

    Raises
    ------
    ValueError
        user_id 为空时抛出。
    """
    if not user_id:
        raise ValueError("user_id 不能为空")

    doc = db["users"].find_one({"user_id": user_id}, {"user_hash": 1, "_id": 0})
    if doc and doc.get("user_hash"):
        return doc["user_hash"]

    new_hash = build_user_hash(user_id)
    db["users"].update_one(
        {"user_id": user_id},
        {"$set": {"user_hash": new_hash}},
        upsert=True,
    )
    logger.info("为用户 %s 生成并存储 user_hash", user_id)
    return new_hash
