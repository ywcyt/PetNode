"""
services/telemetry.py —— 宠物遥测数据查询服务

提供以下内部函数（由路由层调用，不直接暴露为 HTTP 接口）：

  get_pet_summary(db, user_id, pet_id)
      → 宠物最新快照（状态 + 呼吸 + 心率 + 当前事件）

  get_latest_respiration(db, user_id, pet_id)
      → 最新一条呼吸频率采样

  get_respiration_series(db, user_id, pet_id, start, end, limit)
      → 呼吸频率时间序列（支持时间范围 + 条数限制）

  get_latest_heart_rate(db, user_id, pet_id)
      → 最新一条心率采样

  get_heart_rate_series(db, user_id, pet_id, start, end, limit)
      → 心率时间序列（支持时间范围 + 条数限制）

  list_pet_events(db, user_id, pet_id, cursor, limit, event_type, start, end)
      → 事件列表（支持 cursor 分页、时间范围、事件类型过滤）

所有函数均在调用前通过 assert_user_owns_pet() 做权限校验，
抛出 PermissionError 时由路由层转换为 403 响应。
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from .binding import assert_user_can_access_pet

logger = logging.getLogger("flask_server.services.telemetry")

_DEFAULT_SERIES_LIMIT = 50
_MAX_SERIES_LIMIT = 500
_DEFAULT_EVENTS_LIMIT = 20
_MAX_EVENTS_LIMIT = 100


# ────────────────────────────────────────────────
# 内部工具
# ────────────────────────────────────────────────


def _latest_record(
    db, pet_id: str, projection: dict | None = None
) -> dict | None:
    """查询指定设备的最新一条遥测记录。"""
    proj = {**(projection or {}), "_id": 0}
    return db["received_records"].find_one(
        {"device_id": pet_id},
        proj,
        sort=[("timestamp", -1)],
    )


def _clamp_limit(raw: Any, default: int, maximum: int) -> int:
    """解析并限制 limit 参数，若无法转换为整数则抛出 ValueError。"""
    try:
        return min(int(raw) if raw is not None else default, maximum)
    except (TypeError, ValueError):
        raise ValueError(f"limit 必须是整数，收到 {raw!r}")


def _build_ts_query(start: str | None, end: str | None) -> dict:
    """将可选的 start/end 字符串构建为 MongoDB timestamp 过滤条件。"""
    if not start and not end:
        return {}
    ts_q: dict = {}
    if start:
        ts_q["$gte"] = start
    if end:
        ts_q["$lte"] = end
    return {"timestamp": ts_q}


# ────────────────────────────────────────────────
# 公开内部函数
# ────────────────────────────────────────────────


def get_pet_summary(db, user_id: str, pet_id: str) -> dict:
    """获取宠物最新状态快照。

    Parameters
    ----------
    db
        MongoDB 数据库句柄。
    user_id : str
        发起请求的用户 ID（用于权限校验）。
    pet_id : str
        宠物设备 ID。

    Returns
    -------
    dict
        包含以下字段：
        - ``pet_id``                  : str
        - ``dog_status``              : str | None   行为状态
        - ``latest_respiration_bpm``  : float | None 最新呼吸频率
        - ``latest_heart_rate_bpm``   : float | None 最新心率
        - ``current_event``           : str | None   当前事件名称
        - ``current_event_phase``     : str | None   事件阶段
        - ``last_reported_at``        : str | None   最新上报时间

    Raises
    ------
    PermissionError
        用户无权访问该宠物时抛出。
    LookupError
        宠物不存在或暂无数据时抛出。
    """
    assert_user_can_access_pet(db, user_id, pet_id)

    record = _latest_record(db, pet_id)
    if not record:
        raise LookupError(f"宠物 {pet_id} 不存在或暂无数据上报")

    return {
        "pet_id": pet_id,
        "dog_status": record.get("behavior"),
        "latest_respiration_bpm": record.get("resp_rate"),
        "latest_heart_rate_bpm": record.get("heart_rate"),
        "current_event": record.get("event"),
        "current_event_phase": record.get("event_phase"),
        "last_reported_at": record.get("timestamp"),
    }


def get_latest_respiration(db, user_id: str, pet_id: str) -> dict:
    """获取最新一条呼吸频率采样。

    Parameters
    ----------
    db
        MongoDB 数据库句柄。
    user_id : str
        发起请求的用户 ID（用于权限校验）。
    pet_id : str
        宠物设备 ID。

    Returns
    -------
    dict
        包含以下字段：
        - ``pet_id``    : str
        - ``unit``      : str    固定值 ``"bpm"``
        - ``value_bpm`` : float  最新呼吸频率
        - ``ts``        : str    采样时间（ISO 8601）

    Raises
    ------
    PermissionError
        用户无权访问该宠物时抛出。
    LookupError
        暂无呼吸频率数据时抛出。
    """
    assert_user_can_access_pet(db, user_id, pet_id)

    record = db["received_records"].find_one(
        {"device_id": pet_id, "resp_rate": {"$exists": True}},
        {"_id": 0, "timestamp": 1, "resp_rate": 1},
        sort=[("timestamp", -1)],
    )
    if not record:
        raise LookupError(f"宠物 {pet_id} 暂无呼吸频率数据")

    return {
        "pet_id": pet_id,
        "unit": "bpm",
        "value_bpm": record.get("resp_rate"),
        "ts": record.get("timestamp"),
    }


def get_respiration_series(
    db,
    user_id: str,
    pet_id: str,
    start: str | None = None,
    end: str | None = None,
    limit: Any = _DEFAULT_SERIES_LIMIT,
) -> dict:
    """获取呼吸频率时间序列。

    Parameters
    ----------
    db
        MongoDB 数据库句柄。
    user_id : str
        发起请求的用户 ID（用于权限校验）。
    pet_id : str
        宠物设备 ID。
    start : str | None
        起始时间（ISO 8601），可选。
    end : str | None
        结束时间（ISO 8601），可选。
    limit : int
        最多返回条数（默认 50，最大 500）。

    Returns
    -------
    dict
        包含以下字段：
        - ``pet_id``  : str
        - ``unit``    : str          固定值 ``"bpm"``
        - ``count``   : int          实际返回点数
        - ``points``  : list[dict]   ``[{"ts": ..., "value_bpm": ...}]`` 按时间升序

    Raises
    ------
    PermissionError
        用户无权访问该宠物时抛出。
    ValueError
        limit 参数非整数时抛出。
    """
    assert_user_can_access_pet(db, user_id, pet_id)
    limit = _clamp_limit(limit, _DEFAULT_SERIES_LIMIT, _MAX_SERIES_LIMIT)

    query: dict = {"device_id": pet_id}
    query.update(_build_ts_query(start, end))

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

    return {"pet_id": pet_id, "unit": "bpm", "count": len(points), "points": points}


def get_latest_heart_rate(db, user_id: str, pet_id: str) -> dict:
    """获取最新一条心率采样。

    Parameters
    ----------
    db
        MongoDB 数据库句柄。
    user_id : str
        发起请求的用户 ID（用于权限校验）。
    pet_id : str
        宠物设备 ID。

    Returns
    -------
    dict
        包含以下字段：
        - ``pet_id``    : str
        - ``unit``      : str    固定值 ``"bpm"``
        - ``value_bpm`` : float  最新心率
        - ``ts``        : str    采样时间（ISO 8601）

    Raises
    ------
    PermissionError
        用户无权访问该宠物时抛出。
    LookupError
        暂无心率数据时抛出。
    """
    assert_user_can_access_pet(db, user_id, pet_id)

    record = db["received_records"].find_one(
        {"device_id": pet_id, "heart_rate": {"$exists": True}},
        {"_id": 0, "timestamp": 1, "heart_rate": 1},
        sort=[("timestamp", -1)],
    )
    if not record:
        raise LookupError(f"宠物 {pet_id} 暂无心率数据")

    return {
        "pet_id": pet_id,
        "unit": "bpm",
        "value_bpm": record.get("heart_rate"),
        "ts": record.get("timestamp"),
    }


def get_heart_rate_series(
    db,
    user_id: str,
    pet_id: str,
    start: str | None = None,
    end: str | None = None,
    limit: Any = _DEFAULT_SERIES_LIMIT,
) -> dict:
    """获取心率时间序列。

    Parameters
    ----------
    db
        MongoDB 数据库句柄。
    user_id : str
        发起请求的用户 ID（用于权限校验）。
    pet_id : str
        宠物设备 ID。
    start : str | None
        起始时间（ISO 8601），可选。
    end : str | None
        结束时间（ISO 8601），可选。
    limit : int
        最多返回条数（默认 50，最大 500）。

    Returns
    -------
    dict
        包含以下字段：
        - ``pet_id``  : str
        - ``unit``    : str          固定值 ``"bpm"``
        - ``count``   : int          实际返回点数
        - ``points``  : list[dict]   ``[{"ts": ..., "value_bpm": ...}]`` 按时间升序

    Raises
    ------
    PermissionError
        用户无权访问该宠物时抛出。
    ValueError
        limit 参数非整数时抛出。
    """
    assert_user_can_access_pet(db, user_id, pet_id)
    limit = _clamp_limit(limit, _DEFAULT_SERIES_LIMIT, _MAX_SERIES_LIMIT)

    query: dict = {"device_id": pet_id}
    query.update(_build_ts_query(start, end))

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

    return {"pet_id": pet_id, "unit": "bpm", "count": len(points), "points": points}


def list_pet_events(
    db,
    user_id: str,
    pet_id: str,
    cursor: str | None = None,
    limit: Any = _DEFAULT_EVENTS_LIMIT,
    event_type: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """获取宠物事件列表（支持 cursor 分页）。

    Parameters
    ----------
    db
        MongoDB 数据库句柄。
    user_id : str
        发起请求的用户 ID（用于权限校验）。
    pet_id : str
        宠物设备 ID。
    cursor : str | None
        分页游标（上次响应的 next_cursor），优先级高于 start/end。
    limit : int
        每页条数（默认 20，最大 100）。
    event_type : str | None
        过滤事件类型（如 ``"fever"``、``"injury"``），为 None 时返回所有类型。
    start : str | None
        起始时间过滤（ISO 8601），cursor 存在时忽略。
    end : str | None
        结束时间过滤（ISO 8601），cursor 存在时忽略。

    Returns
    -------
    dict
        包含以下字段：
        - ``pet_id``      : str
        - ``items``       : list[dict]  事件项 ``[{"ts", "type", "phase", "behavior"}]``
        - ``next_cursor`` : str | None  下一页游标（无更多数据时为 None）

    Raises
    ------
    PermissionError
        用户无权访问该宠物时抛出。
    ValueError
        limit 参数非整数时抛出。
    """
    assert_user_can_access_pet(db, user_id, pet_id)
    limit = _clamp_limit(limit, _DEFAULT_EVENTS_LIMIT, _MAX_EVENTS_LIMIT)

    query: dict = {"device_id": pet_id}
    if event_type:
        query["event"] = event_type
    else:
        query["event"] = {"$ne": None, "$exists": True, "$type": "string"}

    if cursor:
        query["timestamp"] = {"$lt": cursor}
    elif start or end:
        query.update(_build_ts_query(start, end))

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

    items_data = [
        {
            "event_id": _build_event_id(pet_id, r),
            "ts": r.get("timestamp"),
            "type": r.get("event"),
            "phase": r.get("event_phase"),
            "behavior": r.get("behavior"),
        }
        for r in items
    ]
    event_ids = [x["event_id"] for x in items_data]
    read_set = set()
    if event_ids:
        read_rows = db["pet_event_reads"].find(
            {"user_id": user_id, "pet_id": pet_id, "event_id": {"$in": event_ids}},
            {"_id": 0, "event_id": 1},
        )
        read_set = {x["event_id"] for x in read_rows}
    for item in items_data:
        item["is_read"] = item["event_id"] in read_set

    return {
        "pet_id": pet_id,
        "items": items_data,
        "next_cursor": next_cursor,
    }


def get_temperature_series(
    db,
    user_id: str,
    pet_id: str,
    start: str | None = None,
    end: str | None = None,
    limit: Any = _DEFAULT_SERIES_LIMIT,
) -> dict:
    """获取体温时间序列。"""
    assert_user_can_access_pet(db, user_id, pet_id)
    limit = _clamp_limit(limit, _DEFAULT_SERIES_LIMIT, _MAX_SERIES_LIMIT)

    query: dict = {"device_id": pet_id}
    query.update(_build_ts_query(start, end))
    records = list(
        db["received_records"].find(
            query,
            {"_id": 0, "timestamp": 1, "temperature": 1},
            sort=[("timestamp", 1)],
            limit=limit,
        )
    )
    points = [
        {"ts": r["timestamp"], "value_celsius": r["temperature"]}
        for r in records
        if "temperature" in r
    ]
    return {"pet_id": pet_id, "unit": "celsius", "count": len(points), "points": points}


def get_latest_location(db, user_id: str, pet_id: str) -> dict:
    """获取最新 GPS 位置。"""
    assert_user_can_access_pet(db, user_id, pet_id)
    record = db["received_records"].find_one(
        {"device_id": pet_id, "gps_lat": {"$exists": True}, "gps_lng": {"$exists": True}},
        {"_id": 0, "timestamp": 1, "gps_lat": 1, "gps_lng": 1},
        sort=[("timestamp", -1)],
    )
    if not record:
        raise LookupError(f"宠物 {pet_id} 暂无定位数据")
    return {
        "pet_id": pet_id,
        "lat": record.get("gps_lat"),
        "lng": record.get("gps_lng"),
        "ts": record.get("timestamp"),
    }


def mark_pet_event_as_read(db, user_id: str, pet_id: str, event_id: str) -> dict:
    """标记事件为已读。"""
    assert_user_can_access_pet(db, user_id, pet_id)
    if not event_id:
        raise ValueError("event_id 不能为空")

    db["pet_event_reads"].update_one(
        {"user_id": user_id, "pet_id": pet_id, "event_id": event_id},
        {"$set": {"read_at": _now_iso()}},
        upsert=True,
    )
    return {"status": "marked_read", "event_id": event_id}


def update_pet_profile(db, user_id: str, pet_id: str, updates: dict) -> dict:
    """更新宠物档案（仅 owner）。"""
    allowed = {"pet_name", "avatar_url", "weight", "breed"}
    patch = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not patch:
        raise ValueError("至少提供一个可更新字段")

    owner = db["user_pets"].find_one({"user_id": user_id, "device_id": pet_id}, {"_id": 0})
    if not owner:
        raise PermissionError("仅设备拥有者可修改宠物资料")

    now = _now_iso()
    patch["updated_at"] = now
    db["user_pets"].update_one({"user_id": user_id, "device_id": pet_id}, {"$set": patch})
    db["pets"].update_one({"pet_id": pet_id}, {"$set": patch}, upsert=True)
    latest = db["user_pets"].find_one({"user_id": user_id, "device_id": pet_id}, {"_id": 0})
    return {
        "pet_id": pet_id,
        "pet_name": latest.get("pet_name"),
        "breed": latest.get("breed"),
        "avatar_url": latest.get("avatar_url"),
        "weight": latest.get("weight"),
        "updated_at": now,
    }


def _build_event_id(pet_id: str, row: dict) -> str:
    payload = {
        "pet_id": pet_id,
        "timestamp": row.get("timestamp"),
        "event": row.get("event"),
        "event_phase": row.get("event_phase"),
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
