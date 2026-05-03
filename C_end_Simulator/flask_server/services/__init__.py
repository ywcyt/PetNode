"""
flask_server.services —— 内部服务函数层

按职责分为三个模块：

  identity  → 用户身份规范化与哈希工具
  binding   → 用户与微信/设备的绑定和解绑业务逻辑
  telemetry → 宠物遥测数据查询（呼吸、心率、事件等）

调用约定：
  所有函数接受 MongoDB 数据库句柄（由 flask_server.db.get_db() 提供）作为
  首个参数，保持单职责并支持在测试中注入 mock 数据库。
"""

from .binding import (
    assert_user_owns_pet,
    bind_user_to_device,
    bind_user_to_wechat,
    unbind_user_from_device,
    unbind_user_from_wechat,
)
from .identity import build_user_hash, get_or_create_user_hash, normalize_identity
from .telemetry import (
    get_heart_rate_series,
    get_latest_heart_rate,
    get_latest_respiration,
    get_pet_summary,
    get_respiration_series,
    list_pet_events,
)

__all__ = [
    # identity
    "normalize_identity",
    "build_user_hash",
    "get_or_create_user_hash",
    # binding
    "bind_user_to_wechat",
    "unbind_user_from_wechat",
    "bind_user_to_device",
    "unbind_user_from_device",
    "assert_user_owns_pet",
    # telemetry
    "get_pet_summary",
    "get_latest_respiration",
    "get_respiration_series",
    "get_latest_heart_rate",
    "get_heart_rate_series",
    "list_pet_events",
]
