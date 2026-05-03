"""
blueprints/pets.py —— 宠物遥测数据接口

所有接口均需要有效的 Bearer access_token，且只能访问用户自己关联的宠物。
pet_id 与 received_records 集合中的 device_id 一一对应。

Endpoints
---------
GET /api/v1/pets/<pet_id>/summary
    宠物当前概览（最新快照）。

GET /api/v1/pets/<pet_id>/respiration/latest
    最新一条呼吸频率采样。

GET /api/v1/pets/<pet_id>/respiration/series
    呼吸频率时间序列（支持 start/end/limit 过滤）。

GET /api/v1/pets/<pet_id>/heart-rate/latest
    最新一条心率采样。

GET /api/v1/pets/<pet_id>/heart-rate/series
    心率时间序列（支持 start/end/limit 过滤）。

GET /api/v1/pets/<pet_id>/events
    事件列表（支持 cursor 分页、start/end 时间过滤、event_type 过滤）。

权限模型：
    - user_pets 集合中存在 {user_id, device_id} 记录时，认为用户有权访问该宠物。
    - 如需注册宠物关联，请直接向 MongoDB user_pets 集合写入记录：
        { user_id: "...", device_id: "...", pet_name: "旺财", added_at: "..." }
"""

from __future__ import annotations

import logging

from flask import Blueprint, g, request

from ..auth import require_auth
from ..db import get_db
from ..helpers import err, ok

pets_bp = Blueprint("pets", __name__, url_prefix="/api/v1/pets")
logger = logging.getLogger("flask_server.pets")

_MAX_SERIES_LIMIT = 500
_DEFAULT_SERIES_LIMIT = 50
_DEFAULT_EVENTS_LIMIT = 20
_MAX_EVENTS_LIMIT = 100


# ────────────────── 内部工具 ──────────────────


def _check_pet_access(db, user_id: str, pet_id: str) -> bool:
    """检查 user_id 是否有权访问 pet_id（device_id）。"""
    return (
        db["user_pets"].count_documents(
            {"user_id": user_id, "device_id": pet_id}, limit=1
        )
        > 0
    )


def _latest_record(db, pet_id: str, projection: dict | None = None) -> dict | None:
    """查询指定 device_id 的最新一条记录。"""
    proj = projection or {}
    return db["received_records"].find_one(
        {"device_id": pet_id},
        {**proj, "_id": 0},
        sort=[("timestamp", -1)],
    )


# ────────────────── 路由 ──────────────────


@pets_bp.route("/<pet_id>/summary", methods=["GET"])
@require_auth
def get_pet_summary(pet_id: str):
    """
    GET /api/v1/pets/{pet_id}/summary

    Response data:
        pet_id                string   宠物设备 ID
        dog_status            string   行为状态（sleeping/resting/walking/running）
        latest_respiration_bpm float   最新呼吸频率（次/分钟）
        latest_heart_rate_bpm  float   最新心率（bpm）
        current_event         string|null  当前事件名称（无事件为 null）
        current_event_phase   string|null  事件阶段（onset/peak/recovery，无事件为 null）
        last_reported_at      string   最新数据上报时间（ISO 8601）
    """
    db = get_db()
    if not _check_pet_access(db, g.user_id, pet_id):
        return err(40301, "无权访问该宠物数据，请先在 user_pets 集合中注册设备", 403)

    record = _latest_record(db, pet_id)
    if not record:
        return err(40401, "宠物不存在或暂无数据上报", 404)

    return ok(
        {
            "pet_id": pet_id,
            "dog_status": record.get("behavior"),
            "latest_respiration_bpm": record.get("resp_rate"),
            "latest_heart_rate_bpm": record.get("heart_rate"),
            "current_event": record.get("event"),
            "current_event_phase": record.get("event_phase"),
            "last_reported_at": record.get("timestamp"),
        }
    )


@pets_bp.route("/<pet_id>/respiration/latest", methods=["GET"])
@require_auth
def get_respiration_latest(pet_id: str):
    """
    GET /api/v1/pets/{pet_id}/respiration/latest

    Response data:
        pet_id     string  宠物设备 ID
        unit       string  固定值 "bpm"（次/分钟）
        value_bpm  float   最新呼吸频率值
        ts         string  采样时间（ISO 8601）
    """
    db = get_db()
    if not _check_pet_access(db, g.user_id, pet_id):
        return err(40301, "无权访问该宠物数据，请先在 user_pets 集合中注册设备", 403)

    record = db["received_records"].find_one(
        {"device_id": pet_id, "resp_rate": {"$exists": True}},
        {"_id": 0, "timestamp": 1, "resp_rate": 1},
        sort=[("timestamp", -1)],
    )
    if not record:
        return err(40401, "暂无呼吸频率数据", 404)

    return ok(
        {
            "pet_id": pet_id,
            "unit": "bpm",
            "value_bpm": record.get("resp_rate"),
            "ts": record.get("timestamp"),
        }
    )


@pets_bp.route("/<pet_id>/respiration/series", methods=["GET"])
@require_auth
def get_respiration_series(pet_id: str):
    """
    GET /api/v1/pets/{pet_id}/respiration/series

    Query params:
        start   string  可选  起始时间（ISO 8601），如 2026-05-03T00:00:00
        end     string  可选  结束时间（ISO 8601）
        limit   int     可选  返回条数上限（默认 50，最大 500）

    Response data:
        pet_id  string  宠物设备 ID
        unit    string  固定值 "bpm"
        count   int     实际返回点数
        points  list    [{ts, value_bpm}] 按时间升序排列
    """
    db = get_db()
    if not _check_pet_access(db, g.user_id, pet_id):
        return err(40301, "无权访问该宠物数据，请先在 user_pets 集合中注册设备", 403)

    start = request.args.get("start")
    end = request.args.get("end")
    try:
        limit = min(
            int(request.args.get("limit", _DEFAULT_SERIES_LIMIT)),
            _MAX_SERIES_LIMIT,
        )
    except ValueError:
        return err(42201, "limit 参数必须为整数", 422)

    query: dict = {"device_id": pet_id}
    if start or end:
        ts_q: dict = {}
        if start:
            ts_q["$gte"] = start
        if end:
            ts_q["$lte"] = end
        query["timestamp"] = ts_q

    records = list(
        db["received_records"].find(
            query,
            {"_id": 0, "timestamp": 1, "resp_rate": 1},
            sort=[("timestamp", 1)],
            limit=limit,
        )
    )

    points = [
        {"ts": r["timestamp"], "value_bpm": r["resp_rate"]}
        for r in records
        if "resp_rate" in r
    ]

    return ok(
        {
            "pet_id": pet_id,
            "unit": "bpm",
            "count": len(points),
            "points": points,
        }
    )


@pets_bp.route("/<pet_id>/heart-rate/latest", methods=["GET"])
@require_auth
def get_heart_rate_latest(pet_id: str):
    """
    GET /api/v1/pets/{pet_id}/heart-rate/latest

    Response data:
        pet_id     string  宠物设备 ID
        unit       string  固定值 "bpm"
        value_bpm  float   最新心率值
        ts         string  采样时间（ISO 8601）
    """
    db = get_db()
    if not _check_pet_access(db, g.user_id, pet_id):
        return err(40301, "无权访问该宠物数据，请先在 user_pets 集合中注册设备", 403)

    record = db["received_records"].find_one(
        {"device_id": pet_id, "heart_rate": {"$exists": True}},
        {"_id": 0, "timestamp": 1, "heart_rate": 1},
        sort=[("timestamp", -1)],
    )
    if not record:
        return err(40401, "暂无心率数据", 404)

    return ok(
        {
            "pet_id": pet_id,
            "unit": "bpm",
            "value_bpm": record.get("heart_rate"),
            "ts": record.get("timestamp"),
        }
    )


@pets_bp.route("/<pet_id>/heart-rate/series", methods=["GET"])
@require_auth
def get_heart_rate_series(pet_id: str):
    """
    GET /api/v1/pets/{pet_id}/heart-rate/series

    Query params:
        start   string  可选  起始时间（ISO 8601）
        end     string  可选  结束时间（ISO 8601）
        limit   int     可选  返回条数上限（默认 50，最大 500）

    Response data:
        pet_id  string  宠物设备 ID
        unit    string  固定值 "bpm"
        count   int     实际返回点数
        points  list    [{ts, value_bpm}] 按时间升序排列
    """
    db = get_db()
    if not _check_pet_access(db, g.user_id, pet_id):
        return err(40301, "无权访问该宠物数据，请先在 user_pets 集合中注册设备", 403)

    start = request.args.get("start")
    end = request.args.get("end")
    try:
        limit = min(
            int(request.args.get("limit", _DEFAULT_SERIES_LIMIT)),
            _MAX_SERIES_LIMIT,
        )
    except ValueError:
        return err(42201, "limit 参数必须为整数", 422)

    query: dict = {"device_id": pet_id}
    if start or end:
        ts_q: dict = {}
        if start:
            ts_q["$gte"] = start
        if end:
            ts_q["$lte"] = end
        query["timestamp"] = ts_q

    records = list(
        db["received_records"].find(
            query,
            {"_id": 0, "timestamp": 1, "heart_rate": 1},
            sort=[("timestamp", 1)],
            limit=limit,
        )
    )

    points = [
        {"ts": r["timestamp"], "value_bpm": r["heart_rate"]}
        for r in records
        if "heart_rate" in r
    ]

    return ok(
        {
            "pet_id": pet_id,
            "unit": "bpm",
            "count": len(points),
            "points": points,
        }
    )


@pets_bp.route("/<pet_id>/events", methods=["GET"])
@require_auth
def get_pet_events(pet_id: str):
    """
    GET /api/v1/pets/{pet_id}/events

    Query params:
        start       string  可选  起始时间（ISO 8601）
        end         string  可选  结束时间（ISO 8601）
        event_type  string  可选  过滤事件类型（如 fever / injury）
        cursor      string  可选  分页游标（上次响应的 next_cursor）
        limit       int     可选  每页条数（默认 20，最大 100）

    Response data:
        pet_id      string  宠物设备 ID
        items       list    事件列表，每项包含 ts / type / phase / behavior
        next_cursor string|null  下一页游标（无更多数据时为 null）
    """
    db = get_db()
    if not _check_pet_access(db, g.user_id, pet_id):
        return err(40301, "无权访问该宠物数据，请先在 user_pets 集合中注册设备", 403)

    start = request.args.get("start")
    end = request.args.get("end")
    event_type = request.args.get("event_type")
    cursor = request.args.get("cursor")

    try:
        limit = min(
            int(request.args.get("limit", _DEFAULT_EVENTS_LIMIT)),
            _MAX_EVENTS_LIMIT,
        )
    except ValueError:
        return err(42201, "limit 参数必须为整数", 422)

    # 只返回有 event 的记录（event 不为 null）
    # 当 event_type 指定时直接用精确匹配，否则用排除 null 的条件
    query: dict = {"device_id": pet_id}
    if event_type:
        query["event"] = event_type
    else:
        query["event"] = {"$ne": None, "$exists": True, "$type": "string"}

    # cursor 优先（向前翻页），否则用 start/end
    if cursor:
        query["timestamp"] = {"$lt": cursor}
    elif start or end:
        ts_q: dict = {}
        if start:
            ts_q["$gte"] = start
        if end:
            ts_q["$lte"] = end
        query["timestamp"] = ts_q

    # 多取一条用于判断是否有下一页
    records = list(
        db["received_records"].find(
            query,
            {"_id": 0, "timestamp": 1, "event": 1, "event_phase": 1, "behavior": 1},
            sort=[("timestamp", -1)],
            limit=limit + 1,
        )
    )

    has_more = len(records) > limit
    items = records[:limit]
    next_cursor = items[-1]["timestamp"] if has_more and items else None

    return ok(
        {
            "pet_id": pet_id,
            "items": [
                {
                    "ts": r.get("timestamp"),
                    "type": r.get("event"),
                    "phase": r.get("event_phase"),
                    "behavior": r.get("behavior"),
                }
                for r in items
            ],
            "next_cursor": next_cursor,
        }
    )
