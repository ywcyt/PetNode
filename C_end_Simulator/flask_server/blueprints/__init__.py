"""
blueprints —— vx API 路由蓝图包

包含三个 Blueprint：
  wechat_bp  → /api/v1/wechat/*   微信认证与绑定
  users_bp   → /api/v1/me         当前用户信息
  pets_bp    → /api/v1/pets/*     宠物遥测数据
"""

from .devices import devices_bp
from .family import family_bp
from .pets import pets_bp
from .users import users_bp
from .wechat import wechat_bp

__all__ = ["wechat_bp", "users_bp", "pets_bp", "devices_bp", "family_bp"]
