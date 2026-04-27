"""
user_store.py —— TUI 后端用户管理接口

职责：
  - 用户登录与身份认证（生成 user_id）
  - 确认用户拥有的狗数量（决定引擎线程数）
  - 用户会话状态管理

TUI 前端通过此接口管理用户会话，无需直接操作用户数据。

用法::

    store = UserStore()
    user_id = store.login("alice", 3)       # 登录，3 只狗
    info = store.get_user_info()             # 获取当前用户信息
    store.logout()                           # 登出
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# 默认输出目录
_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output_data"


@dataclass
class UserSession:
    """
    用户会话数据类。

    Attributes
    ----------
    user_id : str
        用户唯一标识（基于用户名生成的哈希值）
    username : str
        用户名
    num_dogs : int
        该用户拥有的狗数量
    logged_in : bool
        是否已登录
    """
    user_id: str = ""
    username: str = ""
    num_dogs: int = 1
    logged_in: bool = False


class UserStore:
    """
    TUI 后端用户管理接口。

    负责：
      - 用户登录验证（生成唯一 user_id）
      - 记录用户的狗数量（引擎据此分配线程）
      - 维护当前会话状态

    Parameters
    ----------
    output_dir : str | Path | None
        output_data 目录路径
    """

    def __init__(self, output_dir: str | Path | None = None) -> None:
        self._output_dir = Path(output_dir) if output_dir else _DEFAULT_OUTPUT_DIR
        self._session: Optional[UserSession] = None

    @staticmethod
    def _generate_user_id(username: str) -> str:
        """
        根据用户名生成确定性的 user_id。

        使用 SHA-256 哈希的前 8 位十六进制字符，
        确保相同用户名始终产生相同的 user_id。

        Parameters
        ----------
        username : str
            用户名

        Returns
        -------
        str
            格式为 ``user_<8 hex chars>`` 的唯一标识
        """
        digest = hashlib.sha256(username.encode("utf-8")).hexdigest()[:8]
        return f"user_{digest}"

    def login(self, username: str, num_dogs: int = 1) -> str:
        """
        用户登录。

        Parameters
        ----------
        username : str
            用户名（非空字符串）
        num_dogs : int
            用户拥有的狗数量（>= 1）

        Returns
        -------
        str
            生成的 user_id

        Raises
        ------
        ValueError
            用户名为空或狗数量无效时
        """
        username = username.strip()
        if not username:
            raise ValueError("用户名不能为空")
        if num_dogs < 1:
            raise ValueError("狗的数量必须 >= 1")

        user_id = self._generate_user_id(username)
        self._session = UserSession(
            user_id=user_id,
            username=username,
            num_dogs=num_dogs,
            logged_in=True,
        )
        return user_id

    def logout(self) -> None:
        """用户登出，清除会话"""
        self._session = None

    @property
    def is_logged_in(self) -> bool:
        """是否有用户已登录"""
        return self._session is not None and self._session.logged_in

    def get_user_info(self) -> Optional[dict]:
        """
        获取当前登录用户信息。

        Returns
        -------
        dict | None
            用户信息字典；未登录时返回 None
        """
        if self._session is None:
            return None
        return asdict(self._session)

    @property
    def user_id(self) -> str:
        """当前登录用户的 user_id（未登录时返回空字符串）"""
        return self._session.user_id if self._session else ""

    @property
    def username(self) -> str:
        """当前登录用户的用户名（未登录时返回空字符串）"""
        return self._session.username if self._session else ""

    @property
    def num_dogs(self) -> int:
        """当前登录用户的狗数量（未登录时返回 0）"""
        return self._session.num_dogs if self._session else 0

    def __repr__(self) -> str:
        if self._session:
            return (
                f"UserStore(user={self._session.username}, "
                f"dogs={self._session.num_dogs}, "
                f"logged_in={self._session.logged_in})"
            )
        return "UserStore(no session)"
