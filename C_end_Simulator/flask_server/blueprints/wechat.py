"""
blueprints/wechat.py —— 微信认证与绑定接口

Endpoints
---------
POST /api/v1/wechat/auth
    接收 vx 端 wx.login() 返回的临时 code，换取微信身份票据。
    若已绑定系统用户，同时返回 access_token。

POST /api/v1/wechat/bind
    将微信身份与系统用户绑定。
    - 若请求头携带有效 Authorization Bearer token，则绑定到对应用户。
    - 否则自动创建新用户并完成绑定，返回 access_token。

POST /api/v1/wechat/unbind
    解除当前用户的微信绑定（需要有效 access_token）。

微信 code2Session 调用行为：
    正式环境：需配置 WECHAT_APP_ID 和 WECHAT_APP_SECRET 环境变量。
    开发/测试：未配置时进入 mock 模式，openid = "mock_openid_{code前8位}"。
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

import jwt
import requests
from flask import Blueprint, g, request
from pymongo.errors import DuplicateKeyError

from ..auth import (
    create_access_token,
    create_wx_identity_token,
    decode_token,
    require_auth,
)
from ..db import get_db
from ..helpers import err, ok
from ..services.binding import bind_user_to_wechat, unbind_user_from_wechat

wechat_bp = Blueprint("wechat", __name__, url_prefix="/api/v1/wechat")
logger = logging.getLogger("flask_server.wechat")

_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


# ────────────────── 内部工具 ──────────────────


def _call_code2session(code: str) -> dict:
    """向微信服务器换取 openid/unionid。

    未配置 WECHAT_APP_ID/SECRET 时进入 mock 模式（便于开发联调）。

    Returns
    -------
    dict  包含 openid（必填）、session_key、可选 unionid

    Raises
    ------
    ValueError          微信返回业务错误（errcode != 0）
    requests.Timeout    微信接口超时
    requests.HTTPError  HTTP 层错误
    """
    app_id = os.environ.get("WECHAT_APP_ID", "")
    app_secret = os.environ.get("WECHAT_APP_SECRET", "")

    if not app_id or not app_secret:
        logger.warning(
            "WECHAT_APP_ID/WECHAT_APP_SECRET 未配置，使用 mock 模式"
        )
        return {
            "openid": f"mock_openid_{code[:8]}",
            "session_key": "mock_session_key",
        }

    resp = requests.get(
        _CODE2SESSION_URL,
        params={
            "appid": app_id,
            "secret": app_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        },
        timeout=5,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errcode", 0) != 0:
        raise ValueError(
            f"WeChat errcode={data['errcode']}: {data.get('errmsg', 'unknown')}"
        )
    return data


# ────────────────── 路由 ──────────────────


@wechat_bp.route("/auth", methods=["POST"])
def wechat_auth():
    """
    POST /api/v1/wechat/auth

    Request body (JSON):
        code  string  必填  wx.login() 返回的临时登录凭证

    Response data:
        is_bound          bool    该微信身份是否已绑定系统用户
        wx_identity_token string  10 分钟有效的微信身份票据
        access_token      string  （仅 is_bound=true 时返回）系统 access_token
        user_id           string  （仅 is_bound=true 时返回）系统用户 ID
    """
    body = request.get_json(force=True, silent=True) or {}
    code: str = (body.get("code") or "").strip()

    if not code:
        return err(42201, "code 参数不能为空", 422)

    # 调用微信 code2Session
    try:
        wx_data = _call_code2session(code)
    except requests.Timeout:
        return err(50001, "微信服务请求超时，请稍后重试", 502)
    except ValueError as exc:
        logger.warning("code2session WeChat error: %s", exc)
        return err(40102, "微信 code 无效或已过期", 400)
    except requests.RequestException as exc:
        logger.error("code2session request failed: %s", exc)
        return err(40102, "微信身份校验失败", 400)

    openid: str = wx_data.get("openid", "")
    unionid: str | None = wx_data.get("unionid") or None

    if not openid:
        return err(40102, "微信未返回 openid", 400)

    # 查询绑定关系
    db = get_db()
    query = {"unionid": unionid} if unionid else {"openid": openid}
    binding = db["wechat_bindings"].find_one(query)

    wx_identity_token = create_wx_identity_token(openid, unionid)

    if binding:
        user_id: str = binding["user_id"]
        access_token = create_access_token(user_id)
        return ok(
            {
                "is_bound": True,
                "wx_identity_token": wx_identity_token,
                "access_token": access_token,
                "user_id": user_id,
            }
        )

    return ok(
        {
            "is_bound": False,
            "wx_identity_token": wx_identity_token,
        }
    )


@wechat_bp.route("/bind", methods=["POST"])
def wechat_bind():
    """
    POST /api/v1/wechat/bind

    Request headers (optional):
        Authorization: Bearer <access_token>
            若已有系统账号，携带此 header 将微信绑定到该账号；
            不携带则自动创建新用户后绑定。

    Request body (JSON):
        wx_identity_token  string  必填  由 /wechat/auth 返回的 10 分钟票据

    Response data:
        bind_status   string  "bound" 或 "already_bound"
        user_id       string  系统用户 ID
        bound_at      string  绑定时间（ISO 8601）
        access_token  string  系统 access_token（新绑定时返回）
    """
    body = request.get_json(force=True, silent=True) or {}
    wx_identity_token: str = (body.get("wx_identity_token") or "").strip()

    if not wx_identity_token:
        return err(42201, "wx_identity_token 参数不能为空", 422)

    # 解码微信身份票据
    try:
        wx_payload = decode_token(wx_identity_token)
        if wx_payload.get("type") != "wx_identity":
            raise jwt.InvalidTokenError("Not a wx_identity token")
    except jwt.ExpiredSignatureError:
        return err(40103, "wx_identity_token 已过期，请重新调用 /wechat/auth", 401)
    except jwt.InvalidTokenError:
        return err(40103, "wx_identity_token 无效，请重新调用 /wechat/auth", 401)

    openid: str = wx_payload["openid"]
    unionid: str | None = wx_payload.get("unionid") or None

    # 可选：从 Authorization header 读取现有用户 token
    auth_header = request.headers.get("Authorization", "")
    user_id: str | None = None

    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
        try:
            access_payload = decode_token(token)
            if access_payload.get("type") != "access":
                return err(40101, "Authorization 中的 token 不是有效的 access_token", 401)
            user_id = access_payload["sub"]
        except jwt.ExpiredSignatureError:
            return err(40101, "access_token 已过期，请重新登录", 401)
        except jwt.InvalidTokenError:
            return err(40101, "access_token 无效，请重新登录", 401)

    db = get_db()

    # 先检查是否已存在绑定记录（在创建新用户之前）
    query = {"unionid": unionid} if unionid else {"openid": openid}
    existing = db["wechat_bindings"].find_one(query)

    if existing:
        # 已绑定：若与当前 user_id 冲突则报错，否则幂等返回
        if user_id and existing["user_id"] != user_id:
            return err(40901, "该微信身份已绑定其他系统账号", 409)
        return ok(
            {
                "bind_status": "already_bound",
                "user_id": existing["user_id"],
                "bound_at": existing.get("bound_at"),
            }
        )

    # 不存在绑定：创建新用户（若无 access_token），再绑定
    if not user_id:
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        user_id = str(uuid.uuid4())
        db["users"].insert_one({"user_id": user_id, "created_at": now_iso})

    try:
        result = bind_user_to_wechat(db, user_id, openid, unionid)
    except PermissionError:
        return err(40901, "该微信身份已绑定其他系统账号", 409)
    except RuntimeError:
        return err(40901, "绑定冲突（并发写入），请稍后重试", 409)

    resp_data = {
        "bind_status": result["bind_status"],
        "user_id": result["user_id"],
        "bound_at": result["bound_at"],
    }
    if result["bind_status"] == "bound":
        resp_data["access_token"] = create_access_token(user_id)

    return ok(resp_data)


@wechat_bp.route("/unbind", methods=["POST"])
@require_auth
def wechat_unbind():
    """
    POST /api/v1/wechat/unbind

    解除当前登录用户的微信绑定。

    Request headers:
        Authorization: Bearer <access_token>  必填

    Response data:
        unbind_status  string  "unbound" 或 "not_bound"
        user_id        string  系统用户 ID
        unbound_at     string|null  解绑时间（ISO 8601）；not_bound 时为 null
    """
    result = unbind_user_from_wechat(get_db(), g.user_id)
    return ok(result)
