from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_family(db, owner_user_id: str) -> dict:
    if not owner_user_id:
        raise ValueError("owner_user_id 不能为空")

    now_iso = _now_iso()
    existing = db["families"].find_one({"owner_user_id": owner_user_id}, {"_id": 0})
    if existing:
        family_id = existing["family_id"]
    else:
        family_id = secrets.token_hex(8)
        db["families"].insert_one(
            {
                "family_id": family_id,
                "owner_user_id": owner_user_id,
                "created_at": now_iso,
            }
        )

    db["family_members"].update_one(
        {"family_id": family_id, "user_id": owner_user_id},
        {
            "$set": {
                "family_id": family_id,
                "user_id": owner_user_id,
                "role": "owner",
                "joined_at": now_iso,
            }
        },
        upsert=True,
    )
    return {"family_id": family_id}


def create_invite_token(db, owner_user_id: str, expires_in: int = 600) -> dict:
    family = db["families"].find_one({"owner_user_id": owner_user_id}, {"_id": 0, "family_id": 1})
    if not family:
        raise LookupError("请先创建家庭组")

    token = secrets.token_urlsafe(24)
    now = _now()
    expires_at = now + timedelta(seconds=max(expires_in, 60))
    db["family_invites"].insert_one(
        {
            "invite_token": token,
            "family_id": family["family_id"],
            "owner_user_id": owner_user_id,
            "created_at": now.isoformat(timespec="seconds"),
            "expires_at": expires_at.isoformat(timespec="seconds"),
        }
    )
    return {"invite_token": token, "expires_in": int((expires_at - now).total_seconds())}


def join_family(db, user_id: str, invite_token: str) -> dict:
    if not user_id or not invite_token:
        raise ValueError("user_id 和 invite_token 不能为空")

    invite = db["family_invites"].find_one({"invite_token": invite_token}, {"_id": 0})
    if not invite:
        raise LookupError("邀请码无效")

    expires_at = datetime.fromisoformat(invite["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if _now() > expires_at:
        raise PermissionError("邀请码已过期")

    if db["family_members"].count_documents({"user_id": user_id}, limit=1) > 0:
        existing = db["family_members"].find_one({"user_id": user_id}, {"_id": 0, "family_id": 1})
        if existing and existing["family_id"] == invite["family_id"]:
            return {"join_status": "already_joined", "family_id": invite["family_id"]}
        raise PermissionError("你已加入其他家庭组")

    now_iso = _now_iso()
    db["family_members"].insert_one(
        {
            "family_id": invite["family_id"],
            "user_id": user_id,
            "role": "member",
            "joined_at": now_iso,
        }
    )
    return {"join_status": "joined", "family_id": invite["family_id"]}


def list_family_members(db, user_id: str) -> dict:
    membership = db["family_members"].find_one({"user_id": user_id}, {"_id": 0, "family_id": 1})
    if not membership:
        raise LookupError("你尚未加入任何家庭组")

    family_id = membership["family_id"]
    rows = list(db["family_members"].find({"family_id": family_id}, {"_id": 0}))
    users = {
        u["user_id"]: u
        for u in db["users"].find(
            {"user_id": {"$in": [x["user_id"] for x in rows]}},
            {"_id": 0, "user_id": 1, "nickname": 1},
        )
    }
    members = [
        {
            "user_id": row["user_id"],
            "nickname": users.get(row["user_id"], {}).get("nickname"),
            "role": row.get("role", "member"),
        }
        for row in rows
    ]
    return {"family_id": family_id, "members": members}


def remove_family_member(db, requester_user_id: str, target_user_id: str) -> dict:
    if not requester_user_id or not target_user_id:
        raise ValueError("user_id 参数不能为空")

    requester = db["family_members"].find_one({"user_id": requester_user_id}, {"_id": 0})
    if not requester:
        raise LookupError("你尚未加入任何家庭组")

    family_id = requester["family_id"]
    target = db["family_members"].find_one(
        {"family_id": family_id, "user_id": target_user_id},
        {"_id": 0},
    )
    if not target:
        raise LookupError("目标成员不存在")

    if target_user_id != requester_user_id and requester.get("role") != "owner":
        raise PermissionError("仅家庭组所有者可移除他人")

    if target.get("role") == "owner" and target_user_id == requester_user_id:
        raise PermissionError("所有者不能退出家庭组，请先转移所有权")

    db["family_members"].delete_one({"family_id": family_id, "user_id": target_user_id})
    return {"status": "removed", "family_id": family_id, "user_id": target_user_id}
