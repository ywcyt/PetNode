"""
HttpExporter —— 🔮 未来阶段占位：发送给远程服务器 API

本文件当前为空壳，留作未来阶段实现。

预期功能：
  - 继承 BaseExporter，实现 export() / flush() / close()
  - 通过 HTTP POST 请求将 SmartCollar 生成的模拟数据上报给 S端（远程服务器）
  - 目标接口示例: POST /api/data  (上报一条或一批记录)
  - 支持断网时将数据缓存到 output_data/offline_cache/ 目录
  - 网络恢复后自动补发缓存数据

与 FileExporter 的关系：
  - FileExporter 是"本地写文件"策略（当前阶段正在使用）
  - HttpExporter 是"远程发 HTTP"策略（未来替换 / 并行使用）
  - 两者都继承自 BaseExporter，调度器 (main.py) 通过统一接口调用，
    无需关心底层是写文件还是发 HTTP（策略模式）

使用方式（未来实现后）::

    exporter = HttpExporter(api_url="https://server.example.com/api/data")
    exporter.export(record)   # POST 一条记录到远程服务器
    exporter.flush()          # 确保所有缓冲数据已发送
    exporter.close()          # 关闭连接
"""

from __future__ import annotations  # 允许使用 Python 3.10+ 类型注解语法

import hashlib  # SHA-256 哈希算法（用于 HMAC 签名）
import hmac  # HMAC 消息认证码（用于防篡改签名）
import json  # JSON 序列化（将 dict 转为 JSON 字符串，用于缓存文件读写）
import logging  # 日志记录
import os  # 操作系统级文件操作（fsync 强制刷盘）
import threading  # 线程锁（Engine 的主循环使用多线程，需要保护共享资源）
from pathlib import Path  # 路径操作（跨平台兼容）

import requests  # HTTP 客户端库（用于发送 POST 请求到 Flask 服务器）

from engine.exporters.base_exporter import BaseExporter  # 导入抽象基类

# ────────────────── 日志 ──────────────────

# 创建本模块专属的日志器（命名空间为 "engine.exporters.http"）
logger = logging.getLogger("engine.exporters.http")

# ────────────────── 常量 ──────────────────

# 默认的 Flask 服务器 API 地址
# "flask-server" 是 docker-compose 中 Flask 容器的服务名（Docker DNS 自动解析）
#_DEFAULT_API_URL = "http://172.28.69.242:5000/api/data"
_DEFAULT_API_URL = os.environ.get("API_URL", "http://flask-server:5000/api/data")

# 默认的离线缓存目录：C_end_Simulator/output_data/offline_cache/
# 当 Flask 服务器不可达时，数据暂存到这个目录，网络恢复后自动补发
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "output_data" / "offline_cache"

# HTTP 请求超时时间（秒）
# 设为 5 秒：太短会导致正常请求也超时，太长会阻塞 Engine 主循环
_REQUEST_TIMEOUT = 5

# 每次 flush() 最多补发多少条缓存记录
# 防止网络恢复后一次性补发过多导致 Flask 过载
_MAX_RETRY_PER_FLUSH = 50

class HttpExporter(BaseExporter):
    """
    通过 HTTP POST 将数据上报至 Flask 服务器。

    Parameters
    ----------
    api_url : str
        Flask 服务器的 API 地址，默认为 http://flask-server:5000/api/data
    cache_dir : str | Path | None
        离线缓存目录，默认为 output_data/offline_cache/
    timeout : int
        HTTP 请求超时秒数，默认 5 秒

    工作流程：
        1. export(record) 尝试 POST 到 Flask
        2. 成功 → 记录日志，结束
        3. 失败（断网/超时/服务器错误）→ 写入离线缓存文件
        4. flush() 被调用时 → 读取缓存文件，逐条补发
        5. 补发成功 → 删除缓存文件
        6. 补发失败 → 保留缓存文件，等下次 flush() 再试
    """

    def __init__(
        self,
        api_url: str = _DEFAULT_API_URL,  # Flask 服务器地址
        cache_dir: str | Path | None = None,  # 离线缓存目录
        timeout: int = _REQUEST_TIMEOUT,  # 请求超时秒数
        api_key: str | None = None,  # API Key，默认从环境变量 API_KEY 读取
        hmac_key: str | None = None,  # HMAC 密钥，默认从环境变量 HMAC_KEY 读取
    ) -> None:
        # 保存 Flask 服务器的 API 地址
        self._url = api_url

        # 保存请求超时时间
        self._timeout = timeout

        # 确定离线缓存目录并自动创建
        self._cache_dir = Path(cache_dir) if cache_dir else _DEFAULT_CACHE_DIR
        # parents=True: 递归创建父目录; exist_ok=True: 目录已存在不报错
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # 创建 requests.Session（复用 TCP 连接，比每次 requests.post() 新建连接更高效）
        # Session 会自动管理 HTTP Keep-Alive，减少握手开销
        self._session = requests.Session()

        # 设置 API Key 鉴权头：优先使用传入参数，其次读环境变量，最后用默认值
        _api_key = api_key or os.environ.get("API_KEY", "petnode_secret_key_2026")
        # 所有通过此 session 发出的请求都会自动带上 Authorization 头
        self._session.headers.update({"Authorization": f"Bearer {_api_key}"})

        # 保存 HMAC 密钥：优先使用传入参数，其次读环境变量，最后用默认值
        self._hmac_key = hmac_key or os.environ.get("HMAC_KEY", "petnode_hmac_secret_2026")

        # 线程锁：Engine 使用 ThreadPoolExecutor 多线程生成数据，
        # 多个线程可能同时调用 export()，需要锁保护缓存文件写入
        self._lock = threading.Lock()

        # 统计计数器（用于日志）
        self._sent_count: int = 0  # 成功发送的记录数
        self._cached_count: int = 0  # 缓存到本地的记录数（发送失败时）
        self._retry_count: int = 0  # 补发成功的记录数

        # 记录初始化日志
        logger.info("HttpExporter 已就绪: url=%s, cache=%s", self._url, self._cache_dir)

    # ── BaseExporter 接口实现 ──

    def export(self, record: dict) -> None:
        """
        导出一条记录：尝试 POST 到 Flask 服务器，失败则缓存到本地文件。

        Parameters
        ----------
        record : dict
            由 SmartCollar.generate_one_record() 产出的 12 字段字典

        流程：
            1. 尝试 HTTP POST record 到 Flask
            2. 成功（状态码 200）→ 计数 +1，记录日志
            3. 失败（网络异常/超时/状态码非 200）→ 调用 _cache_record() 缓存到文件
        """
        try:
            # 使用 _sign_and_post() 计算 HMAC 签名并发送请求
            resp = self._sign_and_post(record)

            # 🆕 新增：拦截鉴权错误，防止密码错误的数据被当成断网缓存起来
            if resp.status_code in [401, 403]:
                logger.error("鉴权失败 (状态码 %d)，服务器拒绝接收数据。请检查 Token。", resp.status_code)
                return

            # raise_for_status(): 如果状态码不是 2xx，抛出 HTTPError 异常
            # 例如 Flask 返回 400（数据格式错误）或 500（服务器内部错误）
            resp.raise_for_status()

            # 发送成功，更新计数器
            self._sent_count += 1

            # 每 100 条打印一次日志（避免刷屏）
            if self._sent_count % 100 == 0:
                logger.info("HTTP 已发送 %d 条记录", self._sent_count)

        except requests.RequestException as exc:
            # 捕获所有 requests 异常：
            #   - ConnectionError: Flask 服务器不可达（断网/容器未启动）
            #   - Timeout: 请求超时（Flask 响应太慢）
            #   - HTTPError: Flask 返回非 2xx 状态码
            # 发送失败，将数据缓存到本地文件
            logger.warning(
                "HTTP 发送失败 (将缓存到本地): %s",  # 日志消息
                exc,  # 异常详情（包含错误类型和原因）
            )
            # 调用缓存方法，将这条记录写入离线缓存文件
            self._cache_record(record)

    def flush(self) -> None:
        """
        补发所有离线缓存的数据。

        当 Engine 主循环定期调用 flush() 时（每 10 ticks），
        会尝试将之前因断网而缓存的数据重新发送到 Flask 服务器。

        流程：
            1. 扫描 offline_cache/ 目录下所有 .jsonl 缓存文件
            2. 逐个读取文件，逐行解析 JSON
            3. 尝试 POST 到 Flask
            4. 成功 → 删除该缓存文件
            5. 失败 → 保留该文件，停止补发（等下次 flush 再试）
            6. 最多补发 _MAX_RETRY_PER_FLUSH 条，防止一次性补发太多
        """
        # 扫描缓存目录下所有 .jsonl 文件，按文件名排序（时间戳排序，先进先出）
        cache_files = sorted(self._cache_dir.glob("*.jsonl"))

        # 没有缓存文件，直接返回
        if not cache_files:
            return

        # 记录开始补发的日志
        logger.info("开始补发离线缓存: %d 个文件", len(cache_files))

        # 本次补发的计数器
        retried = 0

        # 逐个处理缓存文件
        for cache_file in cache_files:
            # 达到单次补发上限，停止（防止 Flask 过载）
            if retried >= _MAX_RETRY_PER_FLUSH:
                logger.info("本次补发已达上限 (%d 条)，剩余下次处理", _MAX_RETRY_PER_FLUSH)
                break

            try:
                # 读取缓存文件的全部内容
                text = cache_file.read_text(encoding="utf-8")

                # 标记本文件是否全部补发成功
                all_sent = True

                # 逐行解析（每行是一条 JSON 记录）
                for line in text.strip().splitlines():
                    # 跳过空行
                    if not line.strip():
                        continue

                    # 将 JSON 字符串反序列化为 dict
                    record = json.loads(line)

                    try:
                        # 尝试重新发送到 Flask（带 HMAC 签名）
                        resp = self._sign_and_post(record)
                        # 检查响应状态码
                        resp.raise_for_status()

                        # 补发成功，更新计数器
                        retried += 1
                        self._retry_count += 1

                    except requests.RequestException:
                        # 补发失败（Flask 仍然不可达），标记本文件未全部发送
                        all_sent = False
                        # 停止处理本文件（后面的记录也不用试了，网络还是不通）
                        break

                # 如果本文件所有记录都补发成功，删除缓存文件
                if all_sent:
                    cache_file.unlink()  # 删除文件
                    logger.info("缓存文件已补发并删除: %s", cache_file.name)
                else:
                    # 有记录补发失败，停止处理后续文件（网络不通，不浪费时间）
                    logger.warning("补发中断（网络仍不可达），剩余缓存保留")
                    break

            except (json.JSONDecodeError, OSError) as exc:
                # 缓存文件损坏或读取失败，记录错误并跳过
                logger.error("读取缓存文件失败: %s, 错误: %s", cache_file.name, exc)
                continue

        # 补发结束，打印汇总日志
        if retried > 0:
            logger.info("本次补发完成: 成功 %d 条, 累计补发 %d 条", retried, self._retry_count)

    def close(self) -> None:
        """
        释放资源：关闭 HTTP Session。

        Engine 停止时（正常结束或 Ctrl-C）会调用此方法。
        关闭 Session 会释放底层的 TCP 连接池。
        """
        # 关闭 requests.Session，释放所有 TCP 连接
        self._session.close()

        # 打印最终统计日志
        logger.info(
            "HttpExporter 已关闭: 发送=%d, 缓存=%d, 补发=%d",
            self._sent_count,  # 成功发送的总条数
            self._cached_count,  # 缓存到本地的总条数
            self._retry_count,  # 补发成功的总条数
        )

    # ── 内部方法 ──

    def _sign_and_post(self, record: dict) -> requests.Response:
        """
        对 record 计算 HMAC-SHA256 签名，并通过 HTTP POST 发送到 Flask 服务器。

        使用 sort_keys=True 保证同一个 dict 每次序列化的 JSON 字符串一致，
        从而保证 Engine 和 Flask 双方对同一条记录算出相同的签名。

        Parameters
        ----------
        record : dict
            要发送的数据记录

        Returns
        -------
        requests.Response
            HTTP 响应对象
        """
        # 将 record 序列化为 JSON bytes
        # sort_keys=True: 保证 key 排序一致，避免同一 dict 因 key 顺序不同产生不同签名
        # ensure_ascii=False: 中文等非 ASCII 字符不转义（节省字节数）
        body_bytes = json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")

        # 用 HMAC-SHA256 计算签名
        sig = hmac.new(
            self._hmac_key.encode("utf-8"),  # 共享密钥
            body_bytes,  # 待签名的请求体
            hashlib.sha256,  # 哈希算法
        ).hexdigest()

        # 发送请求：使用 data=body_bytes 而不是 json=record，
        # 确保发送的字节流与签名时完全一致
        return self._session.post(
            self._url,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Signature": sig,
            },
            timeout=self._timeout,
        )

    def _cache_record(self, record: dict) -> None:
        """
        将一条发送失败的记录缓存到本地文件。

        缓存策略：
          - 每条记录追加到当天的缓存文件中（按天分文件，方便管理）
          - 文件名格式: cache_2025-06-01.jsonl
          - 使用线程锁保护（多线程安全）
          - 写入后立即 fsync 确保数据持久化（断电也不丢）

        Parameters
        ----------
        record : dict
            发送失败的数据记录
        """
        # 从记录中提取时间戳作为文件名的日期部分
        # 如果没有 timestamp 字段，使用 "unknown" 作为默认值
        ts = record.get("timestamp", "unknown")

        # 取日期部分（"2025-06-01T00:01:00" → "2025-06-01"）
        # 如果 timestamp 格式异常，用前 10 个字符兜底
        date_str = ts[:10] if isinstance(ts, str) and len(ts) >= 10 else "unknown"

        # 拼接缓存文件路径：offline_cache/cache_2025-06-01.jsonl
        cache_file = self._cache_dir / f"cache_{date_str}.jsonl"

        # 将 record 序列化为 JSON 字符串
        line = json.dumps(record, ensure_ascii=False)

        # 加锁写入（防止多线程并发写同一个缓存文件）
        with self._lock:
            # 以追加模式打开缓存文件并写入一行
            with open(cache_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")  # 写入 JSON + 换行符
                f.flush()  # 将 Python 缓冲区刷到 OS
                os.fsync(f.fileno())  # 将 OS 缓冲区刷到磁盘（双保险）

        # 更新缓存计数器
        self._cached_count += 1

        # 每 10 条缓存打印一次警告（避免刷屏）
        if self._cached_count % 10 == 0:
            logger.warning("已缓存 %d 条数据到 %s", self._cached_count, self._cache_dir)

    # ── 便利属性 ──

    @property
    def api_url(self) -> str:
        """返回当前连接的 Flask 服务器 API 地址"""
        return self._url

    @property
    def cache_dir(self) -> Path:
        """返回离线缓存目录路径"""
        return self._cache_dir

    def __repr__(self) -> str:
        """返回对象的字符串表示（方便调试打印）"""
        return (
            f"HttpExporter(url={self._url}, "  # API 地址
            f"sent={self._sent_count}, "  # 已发送条数
            f"cached={self._cached_count}, "  # 已缓存条数
            f"retried={self._retry_count})"  # 已补发条数
        )
