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
from ..services.telemetry import (
    get_heart_rate_series,
    get_latest_heart_rate,
    get_latest_respiration,
    get_pet_summary,
    get_respiration_series,
    list_pet_events,
)

pets_bp = Blueprint("pets", __name__, url_prefix="/api/v1/pets")
logger = logging.getLogger("flask_server.pets")


# ────────────────── 路由 ──────────────────


@pets_bp.route("/<pet_id>/summary", methods=["GET"])
@require_auth
def get_pet_summary_route(pet_id: str):
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
    try:
        data = get_pet_summary(get_db(), g.user_id, pet_id)
    except PermissionError:
        return err(40301, "无权访问该宠物数据，请先在 user_pets 集合中注册设备", 403)
    except LookupError:
        return err(40401, "宠物不存在或暂无数据上报", 404)
    return ok(data)


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
    try:
        data = get_latest_respiration(get_db(), g.user_id, pet_id)
    except PermissionError:
        return err(40301, "无权访问该宠物数据，请先在 user_pets 集合中注册设备", 403)
    except LookupError:
        return err(40401, "暂无呼吸频率数据", 404)
    return ok(data)


@pets_bp.route("/<pet_id>/respiration/series", methods=["GET"])
@require_auth
def get_respiration_series_route(pet_id: str):
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
    start = request.args.get("start")
    end = request.args.get("end")
    raw_limit = request.args.get("limit")
    try:
        data = get_respiration_series(get_db(), g.user_id, pet_id, start, end, raw_limit)
    except PermissionError:
        return err(40301, "无权访问该宠物数据，请先在 user_pets 集合中注册设备", 403)
    except ValueError:
        return err(42201, "limit 参数必须为整数", 422)
    return ok(data)


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
    try:
        data = get_latest_heart_rate(get_db(), g.user_id, pet_id)
    except PermissionError:
        return err(40301, "无权访问该宠物数据，请先在 user_pets 集合中注册设备", 403)
    except LookupError:
        return err(40401, "暂无心率数据", 404)
    return ok(data)


@pets_bp.route("/<pet_id>/heart-rate/series", methods=["GET"])
@require_auth
def get_heart_rate_series_route(pet_id: str):
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
    start = request.args.get("start")
    end = request.args.get("end")
    raw_limit = request.args.get("limit")
    try:
        data = get_heart_rate_series(get_db(), g.user_id, pet_id, start, end, raw_limit)
    except PermissionError:
        return err(40301, "无权访问该宠物数据，请先在 user_pets 集合中注册设备", 403)
    except ValueError:
        return err(42201, "limit 参数必须为整数", 422)
    return ok(data)


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
    start = request.args.get("start")
    end = request.args.get("end")
    event_type = request.args.get("event_type")
    cursor = request.args.get("cursor")
    raw_limit = request.args.get("limit")
    try:
        data = list_pet_events(
            get_db(), g.user_id, pet_id,
            cursor=cursor, limit=raw_limit,
            event_type=event_type, start=start, end=end,
        )
    except PermissionError:
        return err(40301, "无权访问该宠物数据，请先在 user_pets 集合中注册设备", 403)
    except ValueError:
        return err(42201, "limit 参数必须为整数", 422)
    return ok(data)
