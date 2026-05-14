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
    assert_user_can_access_pet,
    assert_user_owns_pet,
    bind_user_to_device,
    bind_user_to_wechat,
    list_accessible_pets,
    unbind_user_from_device,
    unbind_user_from_wechat,
)
from .family import (
    create_family,
    create_invite_token,
    join_family,
    list_family_members,
    remove_family_member,
)
from .identity import build_user_hash, get_or_create_user_hash, normalize_identity
from .telemetry import (
    get_latest_location,
    get_heart_rate_series,
    get_latest_heart_rate,
    get_latest_respiration,
    get_pet_summary,
    get_respiration_series,
    get_temperature_series,
    list_pet_events,
    mark_pet_event_as_read,
    update_pet_profile,
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
    "assert_user_can_access_pet",
    "list_accessible_pets",
    # family
    "create_family",
    "create_invite_token",
    "join_family",
    "list_family_members",
    "remove_family_member",
    # telemetry
    "get_pet_summary",
    "get_latest_respiration",
    "get_respiration_series",
    "get_latest_heart_rate",
    "get_heart_rate_series",
    "get_temperature_series",
    "get_latest_location",
    "list_pet_events",
    "mark_pet_event_as_read",
    "update_pet_profile",
]
