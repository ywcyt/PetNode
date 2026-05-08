from __future__ import annotations

from flask import Blueprint, g, request

from ..auth import require_auth
from ..db import get_db
from ..helpers import err, ok
from ..services.family import (
    AlreadyInFamilyError,
    InviteExpiredError,
    create_family,
    create_invite_token,
    join_family,
    list_family_members,
    remove_family_member,
)

family_bp = Blueprint("family", __name__, url_prefix="/api/v1/family")


@family_bp.route("", methods=["POST"])
@require_auth
def create_family_route():
    result = create_family(get_db(), g.user_id)
    return ok(result)


@family_bp.route("/invite", methods=["POST"])
@require_auth
def create_invite_route():
    body = request.get_json(force=True, silent=True) or {}
    expires_in = body.get("expires_in", 600)
    try:
        result = create_invite_token(get_db(), g.user_id, int(expires_in))
    except LookupError:
        return err(40401, "请先创建家庭组", 404)
    except ValueError:
        return err(42201, "expires_in 参数无效", 422)
    return ok(result)


@family_bp.route("/join", methods=["POST"])
@require_auth
def join_family_route():
    body = request.get_json(force=True, silent=True) or {}
    invite_token = (body.get("invite_token") or "").strip()
    if not invite_token:
        return err(42201, "invite_token 参数不能为空", 422)

    try:
        result = join_family(get_db(), g.user_id, invite_token)
    except LookupError:
        return err(40401, "邀请码无效", 404)
    except InviteExpiredError:
        return err(40103, "邀请码已过期", 401)
    except AlreadyInFamilyError:
        return err(40901, "你已加入其他家庭组", 409)
    return ok(result)


@family_bp.route("/members", methods=["GET"])
@require_auth
def list_members_route():
    try:
        result = list_family_members(get_db(), g.user_id)
    except LookupError:
        return err(40401, "你尚未加入任何家庭组", 404)
    return ok(result)


@family_bp.route("/members/<target_user_id>", methods=["DELETE"])
@require_auth
def remove_member_route(target_user_id: str):
    try:
        result = remove_family_member(get_db(), g.user_id, target_user_id)
    except LookupError:
        return err(40401, "目标成员不存在或你尚未加入家庭组", 404)
    except PermissionError:
        return err(40301, "无权限执行该操作", 403)
    return ok(result)
