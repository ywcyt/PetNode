from __future__ import annotations  # 允许使用 Python 3.10+ 的类型注解语法



"""

我们这里，传入的json，张这个样子

{
  "user_id": "user_e3e073dd",        // 用户唯一标识
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

import logging  # Python 标准日志库
import os  # 读取环境变量
from datetime import datetime  # 获取当前时间（用于日志）

from flask import Flask, request, jsonify  # Flask 核心：应用、请求对象、JSON 响应

# 从 storage 子模块导入当前阶段的存储实现（文件存储）
# 未来切换 MySQL 时，只需要改这一行 import
# from storage.file_storage import FileStorage

# Robust import: prefer absolute package import (helps static analysis and tools),
# fall back to relative import when running the module as a script.
try:
    from flask_server.storage.file_storage import FileStorage
except Exception:
    from .storage.file_storage import FileStorage

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

# 从环境变量读取数据存储目录，默认为容器内的 /app/data
# 通过环境变量配置，让 Dockerfile 和 docker-compose 可以灵活指定路径
_DATA_DIR = os.environ.get("DATA_DIR", "/app/data")

# 创建存储实例（当前阶段：FileStorage 写文件）
# 未来切换 MySQL 时：改成 MysqlStorage(host=..., db=...) 即可
storage = FileStorage(data_dir=_DATA_DIR)

# 记录启动日志
logger.info("Flask 数据服务器已初始化，存储目录: %s", _DATA_DIR)

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
        Content-Type: application/json
        Body: {"device_id": "...", "timestamp": "...", "heart_rate": 80, ...}

    Returns
    -------
    JSON 响应:
        成功: {"status": "ok", "message": "数据已保存"}, 200
        失败: {"status": "error", "message": "错误原因"}, 400
    """
    # 引用全局计数器（需要 global 声明才能修改）
    global _total_received

    # ── 第 1 步：解析请求体中的 JSON 数据 ──
    # request.get_json() 会自动解析 Content-Type: application/json 的请求体
    # silent=True 表示解析失败时返回 None 而不是抛异常
    record = request.get_json(force=True, silent=True)

    # ── 第 2 步：校验数据是否合法 ──
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

    # ── 第 3 步：将数据保存到存储层 ──
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

    # ── 第 4 步：更新计数器 ──
    _total_received += 1  # 累加接收总数

    # ── 第 5 步：记录成功日志 ──
    # 记录关键信息：来源 IP、设备 ID、累计接收条数
    logger.info(
        "数据已保存: IP=%s, device_id=%s, 累计=%d 条",
        request.remote_addr,  # 发送方 IP（Engine 容器的 IP）
        record.get("device_id", "未知"),  # 从数据中取设备 ID，取不到显示"未知"
        _total_received,  # 累计接收总条数
    )

    # ── 第 6 步：返回成功响应 ──
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