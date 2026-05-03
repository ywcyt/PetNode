"""
services/binding.py —— 用户绑定与解绑业务逻辑

提供以下内部函数（由路由层调用，不直接暴露为 HTTP 接口）：

  bind_user_to_wechat(db, user_id, openid, unionid)
      → 将系统用户与微信身份绑定（幂等）

  unbind_user_from_wechat(db, user_id)
      → 解除用户的微信绑定

  bind_user_to_device(db, user_id, device_id, pet_name)
      → 将用户与设备（宠物）绑定（幂等）

  unbind_user_from_device(db, user_id, device_id)
      → 解除用户与设备的绑定

  assert_user_owns_pet(db, user_id, pet_id)
      → 断言用户有权访问指定宠物；无权时抛出 PermissionError

存储集合说明：
  wechat_bindings : {user_id, openid, unionid?, bound_at}
  user_pets       : {user_id, device_id, pet_name, added_at}
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger("flask_server.services.binding")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ────────────────────────────────────────────────
# 微信绑定 / 解绑
# ────────────────────────────────────────────────


def bind_user_to_wechat(
    db,
    user_id: str,
    openid: str,
    unionid: str | None = None,
) -> dict:
    """将系统用户与微信身份绑定（幂等操作）。

    Parameters
    ----------
    db
        MongoDB 数据库句柄。
    user_id : str
        系统用户 ID。
    openid : str
        微信 openid（必填）。
    unionid : str | None
        微信 unionid（可选，开放平台场景下使用）。

    Returns
    -------
    dict
        ``{"bind_status": "bound"|"already_bound", "user_id": ..., "bound_at": ...}``

    Raises
    ------
    ValueError
        user_id 或 openid 为空时抛出。
    PermissionError
        该微信身份已绑定**其他**用户时抛出（code 40901）。
    RuntimeError
        并发写入导致唯一索引冲突时抛出。
    """
    if not user_id or not openid:
        raise ValueError("user_id 和 openid 不能为空")

    query = {"unionid": unionid} if unionid else {"openid": openid}
    existing = db["wechat_bindings"].find_one(query)

    if existing:
        if existing["user_id"] != user_id:
            raise PermissionError("该微信身份已绑定其他系统账号")
        return {
            "bind_status": "already_bound",
            "user_id": existing["user_id"],
            "bound_at": existing.get("bound_at"),
        }

    now = _now_iso()
    doc: dict = {"user_id": user_id, "openid": openid, "bound_at": now}
    if unionid:
        doc["unionid"] = unionid

    try:
        db["wechat_bindings"].insert_one(doc)
    except DuplicateKeyError as exc:
        raise RuntimeError("绑定冲突（并发写入），请稍后重试") from exc

    logger.info("用户 %s 绑定微信 openid=%s", user_id, openid[:6] + "***")
    return {"bind_status": "bound", "user_id": user_id, "bound_at": now}


def unbind_user_from_wechat(db, user_id: str) -> dict:
    """解除用户的微信绑定。

    Parameters
    ----------
    db
        MongoDB 数据库句柄。
    user_id : str
        系统用户 ID。

    Returns
    -------
    dict
        ``{"unbind_status": "unbound"|"not_bound", "user_id": ..., "unbound_at": ...}``

    Raises
    ------
    ValueError
        user_id 为空时抛出。
    """
    if not user_id:
        raise ValueError("user_id 不能为空")

    result = db["wechat_bindings"].delete_one({"user_id": user_id})
    if result.deleted_count == 0:
        logger.info("用户 %s 尝试解绑微信但未找到绑定记录", user_id)
        return {"unbind_status": "not_bound", "user_id": user_id, "unbound_at": None}

    now = _now_iso()
    logger.info("用户 %s 解绑微信完成", user_id)
    return {"unbind_status": "unbound", "user_id": user_id, "unbound_at": now}


# ────────────────────────────────────────────────
# 设备（宠物）绑定 / 解绑
# ────────────────────────────────────────────────


def bind_user_to_device(
    db,
    user_id: str,
    device_id: str,
    pet_name: str = "",
) -> dict:
    """将用户与宠物设备绑定（幂等操作）。

    Parameters
    ----------
    db
        MongoDB 数据库句柄。
    user_id : str
        系统用户 ID。
    device_id : str
        设备（项圈）唯一标识，与 received_records.device_id 一致。
    pet_name : str
        宠物昵称（可选）。

    Returns
    -------
    dict
        ``{"bind_status": "bound"|"already_bound", "user_id": ..., "device_id": ..., "added_at": ...}``

    Raises
    ------
    ValueError
        user_id 或 device_id 为空时抛出。
    """
    if not user_id or not device_id:
        raise ValueError("user_id 和 device_id 不能为空")

    existing = db["user_pets"].find_one(
        {"user_id": user_id, "device_id": device_id}, {"_id": 0}
    )
    if existing:
        return {
            "bind_status": "already_bound",
            "user_id": user_id,
            "device_id": device_id,
            "added_at": existing.get("added_at"),
        }

    now = _now_iso()
    db["user_pets"].insert_one(
        {
            "user_id": user_id,
            "device_id": device_id,
            "pet_name": pet_name,
            "added_at": now,
        }
    )
    logger.info("用户 %s 绑定设备 %s（宠物：%s）", user_id, device_id, pet_name or "—")
    return {
        "bind_status": "bound",
        "user_id": user_id,
        "device_id": device_id,
        "added_at": now,
    }


def unbind_user_from_device(db, user_id: str, device_id: str) -> dict:
    """解除用户与宠物设备的绑定。

    Parameters
    ----------
    db
        MongoDB 数据库句柄。
    user_id : str
        系统用户 ID。
    device_id : str
        设备唯一标识。

    Returns
    -------
    dict
        ``{"unbind_status": "unbound"|"not_bound", "user_id": ..., "device_id": ..., "unbound_at": ...}``

    Raises
    ------
    ValueError
        user_id 或 device_id 为空时抛出。
    """
    if not user_id or not device_id:
        raise ValueError("user_id 和 device_id 不能为空")

    result = db["user_pets"].delete_one({"user_id": user_id, "device_id": device_id})
    if result.deleted_count == 0:
        return {
            "unbind_status": "not_bound",
            "user_id": user_id,
            "device_id": device_id,
            "unbound_at": None,
        }

    now = _now_iso()
    logger.info("用户 %s 解绑设备 %s 完成", user_id, device_id)
    return {
        "unbind_status": "unbound",
        "user_id": user_id,
        "device_id": device_id,
        "unbound_at": now,
    }


# ────────────────────────────────────────────────
# 权限断言
# ────────────────────────────────────────────────


def assert_user_owns_pet(db, user_id: str, pet_id: str) -> None:
    """断言用户有权访问指定宠物设备。

    通过查询 user_pets 集合验证 {user_id, device_id} 记录是否存在。

    Parameters
    ----------
    db
        MongoDB 数据库句柄。
    user_id : str
        系统用户 ID（来自 JWT 中的 sub 字段）。
    pet_id : str
        宠物设备 ID（路径参数 pet_id，等同于 device_id）。

    Raises
    ------
    LookupError
        宠物设备记录不存在时抛出（HTTP 404 场景）。
    PermissionError
        用户无权访问该设备时抛出（HTTP 403 场景）。
    """
    if not user_id or not pet_id:
        raise ValueError("user_id 和 pet_id 不能为空")

    has_access = (
        db["user_pets"].count_documents(
            {"user_id": user_id, "device_id": pet_id}, limit=1
        )
        > 0
    )
    if not has_access:
        raise PermissionError(f"用户 {user_id} 无权访问宠物 {pet_id}")
