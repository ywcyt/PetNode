"""
helpers.py —— 统一 JSON 响应助手（供 vx API Blueprint 使用）

所有 vx API 接口均使用相同的 envelope：

成功：
    {
        "code": 0,
        "message": "ok",
        "data": <payload>,
        "server_time": "2026-05-03T12:00:00+00:00"
    }

失败：
    {
        "code": <error_code>,
        "message": "<error_message>",
        "data": null,
        "server_time": "2026-05-03T12:00:00+00:00"
    }
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import jsonify


def _server_time() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ok(data: dict | list) -> tuple:
    """返回统一成功响应 (200)。"""
    return (
        jsonify(
            {
                "code": 0,
                "message": "ok",
                "data": data,
                "server_time": _server_time(),
            }
        ),
        200,
    )


def err(code: int, message: str, http_status: int = 400) -> tuple:
    """返回统一错误响应。

    Parameters
    ----------
    code        : 业务错误码（非 0）
    message     : 可读错误描述
    http_status : HTTP 状态码（默认 400）
    """
    return (
        jsonify(
            {
                "code": code,
                "message": message,
                "data": None,
                "server_time": _server_time(),
            }
        ),
        http_status,
    )
