from __future__ import annotations  # 允许使用 Python 3.10+ 的类型注解语法



"""

我们这里，传入的json，张这个样子

{
  "device_id": "109f156a015a",       // 设备（狗）唯一标识
  "timestamp": "2025-06-01T00:01:00", // ISO 8601 格式的模拟时间戳
  "behavior": "sleeping",             // 行为状态：sleeping/resting/walking/running
  "heart_rate": 66.2,                 // 心率 (bpm)
  "resp_rate": 8.5,                   // 呼吸频率 (次/分钟)
  "temperature": 38.45,               // 体温 (°C)
  "steps": 0,                         // 今日累计步数
  "battery": 100,                     // 电量（当前固定为 100）
  "gps_lat": 29.57,                   // GPS 纬度
  "gps_lng": 106.45,                  // GPS 经度
  "event": null,                      // 当前事件名称（如发烧、受伤等，无事件时为 null）
  "event_phase": null                 // 事件阶段：onset/peak/recovery（无事件时为 null）
}


"""

"""
app = Flask(__name__)

@app.route('/')
def index():
    return 'Welcome! Try /greet/YourName'

@app.route('/greet/<name>')
def greet(name):
    return f'Hello, {name}!'

if __name__ == "__main__":
    app.run(debug=True)

"""


"""
app.py —— PetNode S端 Flask 数据服务器

职责：
  - 接收 Engine 容器通过 HTTP POST 发来的狗项圈模拟数据
  - 将数据保存到存储层（当前阶段：文件；未来：MySQL）
  - 记录每次请求的日志（时间、来源 IP、数据条数等）

与 Engine 的关系：
  - Engine (客户端容器) 通过 HttpExporter 发送 POST /api/data
  - 本 Flask (服务端容器) 接收并持久化
  - 两者是完全独立的 Docker 容器，只通过 HTTP 网络通信

启动方式：
  - docker compose up flask-server
  - 或手动: python app.py
"""

# ────────────────── 导入依赖 ──────────────────

import hashlib  # SHA-256 哈希算法（用于 HMAC 签名验证）
import hmac  # HMAC 消息认证码（用于防篡改验签）
import logging  # Python 标准日志库
import os  # 读取环境变量
from datetime import datetime  # 获取当前时间（用于日志）

from flask import Flask, request, jsonify  # Flask 核心：应用、请求对象、JSON 响应

# 存储层采用策略模式：app.py 只依赖 BaseStorage.save()/close()。
#
# 本周任务：默认改为 MongoDB（MongoStorage）。
# 兼容性：仍保留 FileStorage 作为降级/本地无 Mongo 环境的选项。
#
# 通过环境变量 STORAGE_BACKEND 控制：
#   - STORAGE_BACKEND=mongo  (默认) → MongoStorage
#   - STORAGE_BACKEND=file            → FileStorage

# Robust import: prefer absolute package import (helps static analysis and tools),
# fall back to relative import when running the module as a script.
try:
    from flask_server.storage.file_storage import FileStorage
    from flask_server.storage.mongo_storage import MongoStorage
    from flask_server.storage.mysql_storage import MySQLStorage
except Exception:
    from .storage.file_storage import FileStorage
    from .storage.mongo_storage import MongoStorage
    from .storage.mysql_storage import MySQLStorage

# ────────────────── 日志配置 ──────────────────

# 配置日志格式：时间 + 级别 + 日志器名称 + 消息内容
logging.basicConfig(
    level=logging.INFO,  # 日志级别：INFO 及以上都会输出
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",  # 格式与 Engine 保持一致
    datefmt="%Y-%m-%d %H:%M:%S",  # 时间格式：年-月-日 时:分:秒
)

# 创建本模块专属的日志器（命名空间为 "flask_server"）
logger = logging.getLogger("flask_server")

# ────────────────── 初始化 Flask 应用 ──────────────────

# 创建 Flask 应用实例（__name__ 让 Flask 知道当前模块的位置）
app = Flask(__name__)

# ────────────────── 初始化存储层 ──────────────────

# ── 存储后端选择 ──
# 支持三种存储后端：
#   - STORAGE_BACKEND=file   → FileStorage（本地文件）
#   - STORAGE_BACKEND=mongo  (默认) → MongoStorage（MongoDB）
#   - STORAGE_BACKEND=mysql  → MySQLStorage（MySQL，按日期存储）
_STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "mongo").strip().lower()

# FileStorage 的数据目录（仅在 STORAGE_BACKEND=file 时使用）
_DATA_DIR = os.environ.get("DATA_DIR", "/app/data")

if _STORAGE_BACKEND == "file":
    storage = FileStorage(data_dir=_DATA_DIR)
    logger.info("Flask 数据服务器已初始化：FileStorage, 目录=%s", _DATA_DIR)
elif _STORAGE_BACKEND == "mysql":
    # MySQLStorage 的配置由环境变量提供：MYSQL_HOST / MYSQL_PORT / MYSQL_DB 等
    storage = MySQLStorage()
    logger.info(
        "Flask 数据服务器已初始化：MySQLStorage, host=%s:%s, db=%s",
        os.environ.get("MYSQL_HOST", "localhost"),
        os.environ.get("MYSQL_PORT", "3306"),
        os.environ.get("MYSQL_DB", "petnode"),
    )
else:
    # MongoStorage 的配置由环境变量提供：MONGO_URI / MONGO_DB / MONGO_COLLECTION
    storage = MongoStorage()
    logger.info(
        "Flask 数据服务器已初始化：MongoStorage, uri=%s, db=%s, collection=%s",
        os.environ.get("MONGO_URI", "mongodb://mongodb:27017"),
        os.environ.get("MONGO_DB", "petnode"),
        os.environ.get("MONGO_COLLECTION", "received_records"),
    )

# ────────────────── 统计计数器 ──────────────────

# 记录服务器启动以来接收到的总数据条数（用于日志和健康检查）
_total_received: int = 0

# ────────────────── API 路由 ──────────────────


@app.route("/api/data", methods=["POST"])
def receive_data():
    """
    接收一条狗项圈数据记录。

    Engine 的 HttpExporter 会调用:
        POST http://flask-server:5000/api/data
        Authorization: Bearer <api_key>
        Content-Type: application/json
        Body: {"device_id": "...", "timestamp": "...", "heart_rate": 80, ...}

    Returns
    -------
    JSON 响应:
        成功: {"status": "ok", "message": "数据已保存"}, 200
        失败: {"status": "error", "message": "错误原因"}, 400 / 401
    """
    # 引用全局计数器（需要 global 声明才能修改）
    global _total_received

    # ── 第 0 步：API Key 鉴权 ──
    # 从环境变量读取期望的 API Key，默认值为 petnode_secret_key_2026
    expected_key = os.environ.get("API_KEY", "petnode_secret_key_2026")

    # 从请求头 Authorization 中提取 token（格式为 Bearer <key>）
    auth_header = request.headers.get("Authorization", "")

    # 检查 Authorization 头是否存在且格式正确
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning(
            "鉴权失败（缺少或格式错误的 Authorization 头）: IP=%s",
            request.remote_addr,
        )
        return jsonify({
            "status": "error",
            "message": "缺少 Authorization 头",
        }), 401  # HTTP 状态码 401 Unauthorized

    # 提取 Bearer 后面的 token
    token = auth_header[len("Bearer "):]

    # 校验 token 是否与期望的 API Key 一致
    if token != expected_key:
        logger.warning(
            "鉴权失败（API Key 无效）: IP=%s",
            request.remote_addr,
        )
        return jsonify({
            "status": "error",
            "message": "API Key 无效",
        }), 401  # HTTP 状态码 401 Unauthorized

    # ── 第 1 步：HMAC 签名验证 ──
    # 从环境变量读取 HMAC 密钥，默认值为 petnode_hmac_secret_2026
    hmac_key = os.environ.get("HMAC_KEY", "petnode_hmac_secret_2026")

    # 从请求头中获取 Engine 发来的签名
    incoming_sig = request.headers.get("X-Signature", "")

    # 如果缺少 X-Signature 头，直接拒绝
    if not incoming_sig:
        logger.warning(
            "HMAC 验签失败（缺少 X-Signature 头）: IP=%s",
            request.remote_addr,
        )
        return jsonify({
            "status": "error",
            "message": "缺少 HMAC 签名",
        }), 403  # HTTP 状态码 403 Forbidden

    # 用密钥 + 原始请求体重新计算 HMAC-SHA256
    # request.data 是原始 bytes，必须与 Engine 发送的字节流完全一致
    expected_sig = hmac.new(
        hmac_key.encode("utf-8"),
        request.data,
        hashlib.sha256,
    ).hexdigest()

    # 使用 hmac.compare_digest() 安全对比（防止时序攻击）
    if not hmac.compare_digest(incoming_sig, expected_sig):
        logger.warning(
            "HMAC 验签失败（签名不匹配）: IP=%s",
            request.remote_addr,
        )
        return jsonify({
            "status": "error",
            "message": "HMAC 签名验证失败，数据可能被篡改",
        }), 403  # HTTP 状态码 403 Forbidden

    # ── 第 2 步：解析请求体中的 JSON 数据 ──
    # request.get_json() 会自动解析 Content-Type: application/json 的请求体
    # silent=True 表示解析失败时返回 None 而不是抛异常
    record = request.get_json(force=True, silent=True)

    # ── 第 3 步：校验数据是否合法 ──
    # 如果请求体不是合法的 JSON，或者不是字典类型，返回 400 错误
    if record is None or not isinstance(record, dict):
        # 记录警告日志：谁发了个非法请求
        logger.warning(
            "收到非法请求: IP=%s, Content-Type=%s",
            request.remote_addr,  # 请求来源 IP 地址
            request.content_type,  # 请求的 Content-Type 头
        )
        # 返回 400 Bad Request 错误响应
        return jsonify({
            "status": "error",  # 状态标记
            "message": "请求体必须是合法的 JSON 对象",  # 错误描述
        }), 400  # HTTP 状态码 400

    # ── 第 4 步：将数据保存到存储层 ──
    try:
        # 调用存储层的 save 方法（当前是写文件，未来可能是写 MySQL）
        storage.save(record)
    except Exception as exc:
        # 存储失败时记录错误日志
        logger.error("数据保存失败: %s", exc)
        # 返回 500 Internal Server Error
        return jsonify({
            "status": "error",  # 状态标记
            "message": f"数据保存失败: {exc}",  # 错误原因
        }), 500  # HTTP 状态码 500

    # ── 第 5 步：更新计数器 ──
    _total_received += 1  # 累加接收总数

    # ── 第 6 步：记录成功日志 ──
    # 记录关键信息：来源 IP、设备 ID、累计接收条数
    logger.info(
        "数据已保存: IP=%s, device_id=%s, 累计=%d 条",
        request.remote_addr,  # 发送方 IP（Engine 容器的 IP）
        record.get("device_id", "未知"),  # 从数据中取设备 ID，取不到显示"未知"
        _total_received,  # 累计接收总条数
    )

    # ── 第 7 步：返回成功响应 ──
    return jsonify({
        "status": "ok",  # 状态标记：成功
        "message": "数据已保存",  # 成功描述
    }), 200  # HTTP 状态码 200 OK


@app.route("/api/health", methods=["GET"])
def health_check():
    """
    健康检查接口。

    用途：
      - docker-compose 的 healthcheck 可以定期调用此接口
      - 运维/开发人员可以快速确认 Flask 服务是否正常运行
      - 返回服务状态和统计信息

    调用方式：
        GET http://flask-server:5000/api/health

    Returns
    -------
    JSON 响应:
        {"status": "healthy", "total_received": 123, "timestamp": "2026-03-25 ..."}, 200
    """
    return jsonify({
        "status": "healthy",  # 服务状态：健康
        "total_received": _total_received,  # 累计接收数据条数
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # 当前服务器时间
    }), 200  # HTTP 状态码 200 OK


# ────────────────── 启动入口 ──────────────────

# 当直接运行 python app.py 时执行（而不是被 import 时）
if __name__ == "__main__":
    # 从环境变量读取端口号，默认 5000
    # docker-compose 可以通过 environment 设置不同端口
    port = int(os.environ.get("PORT", 5000))

    # 启动日志：打印监听地址和端口
    logger.info("Flask 数据服务器启动: 0.0.0.0:%d", port)

    # 启动 Flask 开发服务器
    # host="0.0.0.0" 表示监听所有网卡（让其他容器能访问到）
    # debug=False 生产模式（不自动重载、不暴露调试信息）
    app.run(
        host="0.0.0.0",  # 监听地址：所有网卡（容器内必须这样设，否则外部访问不到）
        port=port,  # 监听端口：默认 5000
        debug=False,  # 关闭调试模式（生产环境不能开 debug）
    )