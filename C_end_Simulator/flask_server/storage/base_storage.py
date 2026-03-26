"""
BaseStorage —— 数据存储层的抽象基类（策略模式）

所有 storage（file_storage, mysql_storage …）都必须继承此类并实现抽象方法。
这是策略模式的应用：app.py 只依赖 BaseStorage 接口，
运行时注入具体实现（当前阶段用 FileStorage，未来可替换为 MysqlStorage）。

与 Engine 端的对应关系：
  - Engine 端: BaseExporter  → FileExporter  / HttpExporter(占位)
  - Flask  端: BaseStorage   → FileStorage   / MysqlStorage(占位)
  两端都用同样的策略模式，保持架构一致性。

使用方式：
  子类只需实现 save() 和 close() 两个方法即可。
  app.py 通过 BaseStorage 接口调用，无需关心底层是写文件还是写数据库。
"""

# ────────────────── 导入依赖 ──────────────────

from __future__ import annotations  # 允许使用 Python 3.10+ 的类型注解语法

from abc import ABC, abstractmethod  # ABC = 抽象基类，abstractmethod = 抽象方法装饰器


# ────────────────── 抽象基类定义 ──────────────────

class BaseStorage(ABC):
    """
    数据存储器的统一接口。

    子类必须实现：
      - save(record)  : 保存一条从 Engine 接收到的数据记录
      - close()       : 释放资源（关闭文件句柄 / 断开数据库连接等）

    Parameters（子类构造函数自行定义）
    ----------
    record : dict
        由 Engine 的 SmartCollar.generate_one_record() 产出的字典，
        通过 HttpExporter POST 到 Flask，再由 app.py 传入 storage.save()。
        包含 13 个字段：user_id, device_id, timestamp, behavior,
        heart_rate, resp_rate, temperature, steps, battery,
        gps_lat, gps_lng, event, event_phase
    """

    @abstractmethod
    def save(self, record: dict) -> None:
        """
        保存一条数据记录。

        Parameters
        ----------
        record : dict
            从 Engine 接收到的一条狗项圈数据记录（13 个字段的字典）

        Raises
        ------
        Exception
            存储失败时应抛出异常，由 app.py 捕获并返回 500 错误
        """

    @abstractmethod
    def close(self) -> None:
        """
        释放资源。

        FileStorage: 关闭文件句柄
        MysqlStorage（未来）: 断开数据库连接、关闭连接池
        """