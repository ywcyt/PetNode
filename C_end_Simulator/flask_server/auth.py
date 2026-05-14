"""
auth.py —— JWT 鉴权助手（供 vx API Blueprint 使用）

提供：
  - create_access_token(user_id)      → 7 天有效的系统登录 JWT
  - create_wx_identity_token(...)     → 10 分钟有效的微信身份票据 JWT
  - decode_token(token)               → 解码并验证任意 JWT（不区分类型）
  - require_auth                      → 路由装饰器，验证 Bearer access token
                                        并将 user_id 写入 flask.g.user_id

环境变量：
  JWT_SECRET    JWT 签名密钥（默认 petnode_jwt_secret_2026）
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import g, jsonify, request

logger = logging.getLogger("flask_server.auth")

JWT_ALGORITHM = "HS256"


def _get_secret() -> str:
    return os.environ.get("JWT_SECRET", "petnode_jwt_secret_2026")


# ────────────────── Token 生成 ──────────────────


def create_access_token(user_id: str) -> str:
    """生成 7 天有效的系统 access_token。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(days=7),
    }
    return jwt.encode(payload, _get_secret(), algorithm=JWT_ALGORITHM)


def create_wx_identity_token(openid: str, unionid: str | None) -> str:
    """生成 10 分钟有效的微信身份票据（用于 bind 步骤）。"""
    now = datetime.now(timezone.utc)
    payload = {
        "type": "wx_identity",
        "openid": openid,
        "unionid": unionid,
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, _get_secret(), algorithm=JWT_ALGORITHM)


# ────────────────── Token 解码 ──────────────────


def decode_token(token: str) -> dict:
    """解码并验证 JWT，返回 payload dict。

    Raises
    ------
    jwt.ExpiredSignatureError   Token 已过期
    jwt.InvalidTokenError       Token 无效（签名、格式等）
    """
    return jwt.decode(token, _get_secret(), algorithms=[JWT_ALGORITHM])


# ────────────────── 路由装饰器 ──────────────────


def require_auth(f):
    """路由装饰器：要求请求头携带有效 Bearer access_token。

    验证通过后将 user_id 写入 flask.g.user_id，供路由函数使用。

    失败响应：
        401 {"code": 40101, "message": "..."}
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return (
                jsonify({"code": 40101, "message": "未授权，请先登录", "data": None}),
                401,
            )
        token = auth_header[len("Bearer "):]
        try:
            payload = decode_token(token)
            if payload.get("type") != "access":
                raise jwt.InvalidTokenError("Not an access token")
            g.user_id = payload.get("sub")
            if not g.user_id:
                raise jwt.InvalidTokenError("Token missing sub claim")
        except jwt.ExpiredSignatureError:
            return (
                jsonify({"code": 40101, "message": "Token 已过期，请重新登录", "data": None}),
                401,
            )
        except jwt.InvalidTokenError:
            return (
                jsonify({"code": 40101, "message": "Token 无效，请重新登录", "data": None}),
                401,
            )
        return f(*args, **kwargs)

    return decorated
