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

from pymongo.errors import DuplicateKeyError

from ..helpers import now_iso as _now_iso

logger = logging.getLogger("flask_server.services.binding")


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
    device_id: str | None = None,
    pet_name: str = "",
    breed: str = "",
    avatar_url: str = "",
    weight: float | None = None,
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
    if not user_id:
        raise ValueError("user_id 不能为空")

    resolved_device_id = (device_id or "").strip()
    if not resolved_device_id:
        resolved_device_id = _allocate_unbound_device_id(db)
    if not resolved_device_id:
        raise ValueError("当前无可分配设备，请先让设备上报数据")

    if not pet_name:
        pet_name = f"宠物-{resolved_device_id[:6]}"

    existing_owner = db["user_pets"].find_one(
        {"device_id": resolved_device_id},
        {"_id": 0, "user_id": 1, "added_at": 1, "pet_name": 1, "breed": 1, "avatar_url": 1, "weight": 1},
    )
    if existing_owner and existing_owner.get("user_id") != user_id:
        raise PermissionError("该设备已被其他用户认领")

    existing = db["user_pets"].find_one(
        {"user_id": user_id, "device_id": resolved_device_id}, {"_id": 0}
    )
    if existing:
        update_doc: dict = {"updated_at": _now_iso()}
        if pet_name is not None:
            update_doc["pet_name"] = pet_name
        if breed is not None:
            update_doc["breed"] = breed
        if avatar_url is not None:
            update_doc["avatar_url"] = avatar_url
        if weight is not None:
            update_doc["weight"] = weight
        if update_doc:  # 只有存在待更新字段时才执行
            db["user_pets"].update_one(
                {"user_id": user_id, "device_id": resolved_device_id},
                {"$set": update_doc},
            )
        return {
            "bind_status": "already_bound",
            "user_id": user_id,
            "device_id": resolved_device_id,
            "pet_id": resolved_device_id,
            "added_at": existing.get("added_at"),
        }

    now = _now_iso()
    doc = {
        "user_id": user_id,
        "device_id": resolved_device_id,
        "pet_name": pet_name,
        "breed": breed,
        "avatar_url": avatar_url,
        "added_at": now,
        "updated_at": now,
    }
    if weight is not None:
        doc["weight"] = weight
    try:
        db["user_pets"].insert_one(doc)
    except DuplicateKeyError as exc:
        raise RuntimeError("设备绑定冲突，请稍后重试") from exc

    pet_set = {
        "pet_id": resolved_device_id,
        "device_id": resolved_device_id,
        "user_id": user_id,
        "pet_name": pet_name,
        "breed": breed,
        "avatar_url": avatar_url,
        "updated_at": now,
    }
    if weight is not None:
        pet_set["weight"] = weight
    db["pets"].update_one(
        {"pet_id": resolved_device_id},
        {"$set": pet_set, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    logger.info("用户 %s 绑定设备 %s（宠物：%s）", user_id, resolved_device_id, pet_name or "—")
    return {
        "bind_status": "bound",
        "user_id": user_id,
        "device_id": resolved_device_id,
        "pet_id": resolved_device_id,
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
    db["pets"].delete_one({"pet_id": device_id, "user_id": user_id})
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


def _allocate_unbound_device_id(db) -> str | None:
    """从已上报数据中分配一个未被认领的设备 ID（最多扫描 2000 条）。"""
    used = set(db["user_pets"].distinct("device_id"))
    seen: set[str] = set()
    cursor = db["received_records"].find(
        {"device_id": {"$exists": True, "$ne": None, "$nin": list(used) if used else []}},
        {"_id": 0, "device_id": 1},
    ).sort("device_id", 1).limit(2000)
    for row in cursor:
        device_id = str(row.get("device_id") or "").strip()
        if not device_id or device_id in seen:
            continue
        seen.add(device_id)
        if device_id not in used:
            return device_id
    return None


def assert_user_can_access_pet(db, user_id: str, pet_id: str) -> None:
    """断言用户可访问宠物：本人绑定或同家庭共享。"""
    if not user_id or not pet_id:
        raise ValueError("user_id 和 pet_id 不能为空")

    if db["user_pets"].count_documents({"user_id": user_id, "device_id": pet_id}, limit=1) > 0:
        return

    owner = db["user_pets"].find_one({"device_id": pet_id}, {"_id": 0, "user_id": 1})
    if not owner:
        raise PermissionError(f"宠物 {pet_id} 未绑定，用户 {user_id} 无权访问")

    family_ids = db["family_members"].distinct("family_id", {"user_id": user_id})
    if not family_ids:
        raise PermissionError(f"用户 {user_id} 无权访问宠物 {pet_id}")

    same_family = db["family_members"].count_documents(
        {"user_id": owner["user_id"], "family_id": {"$in": family_ids}},
        limit=1,
    ) > 0
    if not same_family:
        raise PermissionError(f"用户 {user_id} 无权访问宠物 {pet_id}")


def list_accessible_pets(db, user_id: str) -> list[dict]:
    """列出用户可访问的宠物（本人 + 家庭共享）。"""
    own = list(db["user_pets"].find({"user_id": user_id}, {"_id": 0}))
    family_ids = db["family_members"].distinct("family_id", {"user_id": user_id})
    shared: list[dict] = []
    if family_ids:
        member_user_ids = db["family_members"].distinct("user_id", {"family_id": {"$in": family_ids}})
        shared = list(
            db["user_pets"].find(
                {"user_id": {"$in": member_user_ids, "$ne": user_id}},
                {"_id": 0},
            )
        )

    merged: dict[str, dict] = {}
    for item in own:
        merged[item["device_id"]] = {**item, "access_mode": "owner"}
    for item in shared:
        merged.setdefault(item["device_id"], {**item, "access_mode": "family"})
    return list(merged.values())
