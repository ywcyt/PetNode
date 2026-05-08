from __future__ import annotations

from flask import Blueprint, g, request

from ..auth import require_auth
from ..db import get_db
from ..helpers import err, ok
from ..services.binding import bind_user_to_device, unbind_user_from_device

devices_bp = Blueprint("devices", __name__, url_prefix="/api/v1/devices")


@devices_bp.route("/bind", methods=["POST"])
@require_auth
def bind_device():
    body = request.get_json(force=True, silent=True) or {}
    device_id = (body.get("device_id") or "").strip() or None
    pet_name = (body.get("pet_name") or "").strip()
    breed = (body.get("breed") or "").strip()
    avatar_url = (body.get("avatar_url") or "").strip()
    weight = body.get("weight")

    try:
        if weight is not None:
            weight = float(weight)
        result = bind_user_to_device(
            get_db(),
            user_id=g.user_id,
            device_id=device_id,
            pet_name=pet_name,
            breed=breed,
            avatar_url=avatar_url,
            weight=weight,
        )
    except PermissionError:
        return err(40901, "该设备已被其他用户认领", 409)
    except RuntimeError:
        return err(40901, "绑定冲突，请稍后重试", 409)
    except ValueError as exc:
        return err(42201, str(exc), 422)

    return ok(
        {
            "pet_id": result["pet_id"],
            "device_id": result["device_id"],
            "bind_status": result["bind_status"],
            "added_at": result["added_at"],
        }
    )


@devices_bp.route("/<device_id>/unbind", methods=["POST"])
@require_auth
def unbind_device(device_id: str):
    try:
        result = unbind_user_from_device(get_db(), g.user_id, device_id)
    except ValueError as exc:
        return err(42201, str(exc), 422)

    return ok(
        {
            "device_id": result["device_id"],
            "unbind_status": result["unbind_status"],
            "unbound_at": result["unbound_at"],
        }
    )
