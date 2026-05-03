"""
blueprints/users.py —— 当前用户信息接口

Endpoints
---------
GET /api/v1/me
    返回当前登录用户的基础信息及其关联宠物列表。
    需要有效的 Bearer access_token。
"""

from __future__ import annotations

import logging

from flask import Blueprint, g

from ..auth import require_auth
from ..db import get_db
from ..helpers import ok

users_bp = Blueprint("users", __name__, url_prefix="/api/v1")
logger = logging.getLogger("flask_server.users")


@users_bp.route("/me", methods=["GET"])
@require_auth
def get_me():
    """
    GET /api/v1/me

    Headers:
        Authorization: Bearer <access_token>  必填

    Response data:
        user_id     string        系统用户 ID
        nickname    string|null   昵称（如有）
        created_at  string|null   账号创建时间（ISO 8601）
        pets        list          已注册宠物列表，每项包含 device_id / pet_name
    """
    db = get_db()
    user = db["users"].find_one({"user_id": g.user_id}, {"_id": 0})
    pets = list(
        db["user_pets"].find(
            {"user_id": g.user_id},
            {"_id": 0, "user_id": 0},
        )
    )

    return ok(
        {
            "user_id": g.user_id,
            "nickname": user.get("nickname") if user else None,
            "created_at": user.get("created_at") if user else None,
            "pets": pets,
        }
    )
