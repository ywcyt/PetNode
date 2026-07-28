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
import json  # JSON 序列化（DeepSeek API 调用等）
import logging  # Python 标准日志库
import os  # 读取环境变量
import urllib.request  # HTTP 客户端（调用 DeepSeek API）
from datetime import datetime  # 获取当前时间（用于日志）

from flask import Flask, request, jsonify  # Flask 核心：应用、请求对象、JSON 响应
from flask_cors import CORS  # 跨域支持


# Robust import: prefer absolute package import (helps static analysis and tools),
# fall back to relative import when running the module as a script.
try:
    from flask_server.storage.mongo_storage import MongoStorage
    from flask_server.storage.mysql_storage import MySQLStorage
except Exception:
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
CORS(app, origins="*")  # 允许前端跨域请求（生产环境应限定具体域名）


# ────────────────── CORS 支持（允许 Web 前端跨域调用）──────────────────

@app.after_request
def _add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response


# ────────────────── 初始化存储层（懒加载，避免启动时 DB 不可达导致崩溃）──────────────────

# MongoDB 负责全量实时数据；MySQL 负责静态档案与异常信息。


class _LazyProxy:
    """延迟初始化代理，首次访问时才创建真正的存储实例。"""
    def __init__(self, factory):
        self._factory = factory
        self._instance = None

    def __getattr__(self, name):
        if self._instance is None:
            self._instance = self._factory()
        return getattr(self._instance, name)


mongo_storage = _LazyProxy(MongoStorage)
mysql_storage = _LazyProxy(MySQLStorage)


def _persist_record(record: dict) -> None:
    """Mongo 保存全量实时数据；MySQL 保存静态信息和异常信息。"""
    mongo_storage.save(record)
    try:
        mysql_storage.save(record)
    except Exception as exc:
        logger.warning("MySQL 持久化失败（Mongo 已保存）: %s", exc)


def _parse_iso_datetime(value: str | None, field_name: str) -> datetime | None:
    """解析 ISO 8601 时间；空值返回 None，非法值抛 ValueError。"""
    if value is None:
        return None

    text = value.strip()
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须是合法的 ISO 8601 时间") from exc

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _normalize_json_value(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_json_value(item) for key, item in value.items()}
    return value


def _build_query_response(source: str, kind: str, payload):
    return jsonify({
        "status": "ok",
        "source": source,
        "kind": kind,
        "count": len(payload) if isinstance(payload, list) else None,
        "data": _normalize_json_value(payload),
    }), 200


def _first_query_arg(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = request.args.get(name)
        if value is not None and str(value).strip():
            return value
    return default


def _handle_query_request(
    default_user_key: str | None = None,
    default_device_key: str | None = None,
    source_override: str | None = None,
    kind_override: str | None = None,
):
    source = (source_override or request.args.get("source", "mongo")).strip().lower()
    kind = (kind_override or request.args.get("kind", "records")).strip().lower()
    user_key = _first_query_arg("user_id", "user_key", default=default_user_key)
    device_key = _first_query_arg("device_id", "device_key", default=default_device_key)

    try:
        limit = int(request.args.get("limit", "100"))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        return jsonify({"status": "error", "message": "limit/offset 必须是整数"}), 400

    try:
        start_time = _parse_iso_datetime(request.args.get("start_time"), "start_time")
        end_time = _parse_iso_datetime(request.args.get("end_time"), "end_time")
    except ValueError:
        return jsonify({"status": "error", "message": "start_time/end_time 必须是合法的 ISO 8601 时间"}), 400

    if source == "mongo":
        if kind not in {"records", "stream"}:
            return jsonify({"status": "error", "message": "Mongo 仅支持 kind=records"}), 400

        items = mongo_storage.query_records(
            user_id=user_key,
            device_id=device_key,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )
        return _build_query_response("mongo", "records", items)

    if source == "mysql":
        if kind in {"profile", "static"}:
            profile = mysql_storage.query_profile(user_key=user_key, device_key=device_key)
            return _build_query_response("mysql", "profile", profile)

        if kind in {"records", "anomalies", "anomaly"}:
            items = mysql_storage.query_anomalies(
                user_key=user_key,
                device_key=device_key,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                offset=offset,
            )
            return _build_query_response("mysql", "anomalies", items)

        return jsonify({"status": "error", "message": "Mysql 仅支持 kind=records/anomalies/profile"}), 400

    return jsonify({"status": "error", "message": "source 只能是 mongo 或 mysql"}), 400

# ────────────────── 统计计数器 ──────────────────

# 记录服务器启动以来接收到的总数据条数（用于日志和健康检查）
_total_received: int = 0

# ────────────────── 注册 vx API Blueprint ──────────────────

# 将微信认证、用户信息、宠物遥测三个 Blueprint 挂载到 Flask 应用。
# 路由前缀由各 Blueprint 自身定义（/api/v1/wechat/* / /api/v1/me / /api/v1/pets/*）。
try:
    from flask_server.blueprints import wechat_bp, users_bp, pets_bp, devices_bp, family_bp, admin_bp
    from flask_server.db import ensure_indexes
except ImportError:
    from .blueprints import wechat_bp, users_bp, pets_bp, devices_bp, family_bp, admin_bp
    from .db import ensure_indexes

app.register_blueprint(wechat_bp)
app.register_blueprint(users_bp)
app.register_blueprint(pets_bp)
app.register_blueprint(devices_bp)
app.register_blueprint(family_bp)
app.register_blueprint(admin_bp)

# 在启动时尝试创建 MongoDB 索引。
try:
    ensure_indexes()
except Exception as _idx_exc:
    logger.warning("vx API 索引初始化出现意外异常: %s", _idx_exc)

# 启动时自动清理旧遥测数据（Engine 重启后模拟时钟重置，旧数据时间戳可能干扰查询）
if os.environ.get("CLEAN_ON_STARTUP", "").lower() in ("1", "true", "yes"):
    try:
        deleted = mongo_storage.clean_all_records()
        logger.info("启动清理完成: 删除了 %d 条旧记录", deleted)
    except Exception as _clean_exc:
        logger.warning("启动清理失败（MongoDB 可能尚未就绪）: %s", _clean_exc)

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
        # Mongo 负责实时全量数据，MySQL 负责静态信息与异常信息
        _persist_record(record)
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


# ────────────────── AI Chat 端点 ──────────────────

import uuid
import time as _time

def _chat_collection():
    """获取 MongoDB 中的 chat 集合（延迟初始化，兼容 LazyProxy）。"""
    try:
        db = mongo_storage._collection.database
        return db["chat_questions"]
    except Exception:
        # fallback: 通过 pymongo 直接连接
        from pymongo import MongoClient
        uri = os.environ.get("MONGO_URI", "mongodb://mongodb:27017")
        db_name = os.environ.get("MONGO_DB", "petnode")
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        return client[db_name]["chat_questions"]


@app.route("/api/chat", methods=["POST"])
def chat_ask():
    """
    AI 智能问答 —— 接收问题，查询实时数据，调用 DeepSeek 返回分析结果。

    POST /api/chat
    Body: {"message": "哪些设备体温异常？"}

    Returns: {"status": "ok", "answer": "...", "question_id": "..."}
    """
    import json as _json

    body = request.get_json(silent=True)
    if not body or not isinstance(body, dict):
        return jsonify({"status": "error", "message": "请求体必须是 JSON 对象"}), 400

    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"status": "error", "message": "message 不能为空"}), 400

    # ── 1. 收集设备实时数据作为分析上下文 ──
    data_context = _build_data_context()

    # ── 2. 存入 MongoDB ──
    qid = uuid.uuid4().hex[:12]
    now_utc = datetime.utcnow().isoformat()
    doc = {
        "question_id": qid,
        "message": message,
        "answer": None,
        "status": "pending",
        "created_at": now_utc,
        "answered_at": None,
    }
    try:
        _chat_collection().insert_one(doc)
    except Exception as exc:
        logger.error("Chat 问题写入失败: %s", exc)

    # ── 3. 调用 DeepSeek API ──
    try:
        answer = _call_deepseek(message, data_context)
        # 更新 MongoDB
        _chat_collection().update_one(
            {"question_id": qid},
            {"$set": {
                "answer": answer,
                "status": "answered",
                "answered_at": datetime.utcnow().isoformat(),
            }},
        )
        logger.info("Chat 已回复: qid=%s, len=%d", qid, len(answer))
        return jsonify({
            "status": "ok",
            "question_id": qid,
            "answer": answer,
        }), 200
    except Exception as exc:
        logger.error("DeepSeek 调用失败: %s", exc)
        error_msg = f"⚠️ AI 服务暂时不可用：{exc}"
        _chat_collection().update_one(
            {"question_id": qid},
            {"$set": {
                "answer": error_msg,
                "status": "answered",
                "answered_at": datetime.utcnow().isoformat(),
            }},
        )
        return jsonify({
            "status": "ok",
            "question_id": qid,
            "answer": error_msg,
        }), 200


def _build_data_context() -> str:
    """从 MongoDB 提取设备实时数据，构建供 AI 分析的文本上下文。"""
    try:
        col = mongo_storage._collection
        # 最近 200 条记录
        records = list(col.find({}, {"_id": 0}).sort("_id", -1).limit(200))
        if not records:
            return "（暂无设备数据）"

        from collections import defaultdict
        devices = defaultdict(lambda: {
            "hr": [], "tmp": [], "rr": [], "steps": 0, "bat": 0, "beh": "", "events": 0
        })
        for r in records:
            d = devices[r["device_id"]]
            d["hr"].append(r.get("heart_rate") or 0)
            d["tmp"].append(r.get("temperature") or 0)
            d["rr"].append(r.get("resp_rate") or 0)
            d["steps"] = max(d["steps"], r.get("steps") or 0)
            d["bat"] = r.get("battery") or 0
            d["beh"] = r.get("behavior", "unknown") or "unknown"
            if r.get("event"):
                d["events"] += 1

        lines = [f"当前共 {len(devices)} 台设备，最近 {len(records)} 条采样：\n"]
        all_hr, all_tmp = [], []
        for did in sorted(devices.keys()):
            d = devices[did]
            n = len(d["hr"])
            avg_hr = sum(d["hr"]) / n
            avg_tmp = sum(d["tmp"]) / n
            avg_rr = sum(d["rr"]) / n
            all_hr.extend(d["hr"])
            all_tmp.extend(d["tmp"])
            alerts = []
            if avg_tmp > 39.5: alerts.append("发热")
            if max(d["tmp"]) > 41: alerts.append("高温峰值!")
            if avg_hr > 130: alerts.append("心率过高")
            if avg_hr < 65: alerts.append("心率过低")
            status = ", ".join(alerts) if alerts else "正常"
            lines.append(
                f"  {did}: 均心率{avg_hr:.0f}bpm, 均体温{avg_tmp:.1f}°C(峰值{max(d['tmp']):.1f}), "
                f"均呼吸{avg_rr:.0f}次/分, 步数{d['steps']}, 电量{d['bat']}%, "
                f"行为{d['beh']}, 事件{d['events']}次 → {status}"
            )
        lines.append(f"\n全局: 心率{sum(all_hr)/len(all_hr):.0f}({min(all_hr)}-{max(all_hr)})bpm, "
                      f"体温{sum(all_tmp)/len(all_tmp):.1f}({min(all_tmp):.1f}-{max(all_tmp):.1f})°C")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("构建数据上下文失败: %s", exc)
        return f"（数据查询异常: {exc}）"


def _call_deepseek(question: str, data_context: str) -> str:
    """调用 DeepSeek API 进行数据分析。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY")

    system_prompt = (
        "你是 PetNode 宠物健康监测系统的 AI 分析师。"
        "根据提供的设备实时遥测数据，回答用户关于宠物（狗）健康状态的问题。"
        "分析要点：心率、体温、呼吸频率、行为模式、异常事件、设备电量。"
        "回答简洁专业，用中文，可用 Markdown 格式。"
        "体温 > 39.5°C 为发热，心率 > 130 或 < 60 需关注，呼吸 > 35 需关注。"
        "若数据不足以判断，请诚实说明。"
    )

    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"实时遥测数据：\n\n{data_context}\n\n用户问题：{question}\n\n请分析并回答。"},
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"]


@app.route("/api/chat", methods=["GET"])
def chat_poll():
    """
    轮询答案。

    GET /api/chat?qid=<question_id>
    GET /api/chat?qid=latest  → 返回最新答案

    Returns: {"status": "pending"} 或 {"status": "ok", "answer": "...", "analysis": {...}}
    """
    qid = request.args.get("qid", "").strip()
    col = _chat_collection()
    if qid == "latest":
        doc = col.find_one({"status": "answered"}, sort=[("answered_at", -1)])
    else:
        if not qid:
            return jsonify({"status": "error", "message": "qid 参数必填"}), 400
        doc = col.find_one({"question_id": qid})

    if not doc:
        return jsonify({"status": "error", "message": "问题不存在"}), 404

    if doc["status"] == "pending":
        return jsonify({"question_id": doc["question_id"], "status": "pending"}), 200

    return jsonify({
        "question_id": doc["question_id"],
        "status": "ok",
        "question": doc["message"],
        "answer": doc["answer"],
        "analysis": doc.get("analysis"),
        "created_at": doc["created_at"],
        "answered_at": doc.get("answered_at"),
    }), 200


@app.route("/api/chat/pending", methods=["GET"])
def chat_pending():
    """
    返回所有待处理问题（供 AI 终端调用）。

    GET /api/chat/pending

    Returns: {"pending": [{"question_id": "...", "message": "...", "created_at": "..."}]}
    """
    col = _chat_collection()
    docs = list(col.find({"status": "pending"}, sort=[("created_at", 1)]).limit(20))
    pending = [{
        "question_id": d["question_id"],
        "message": d["message"],
        "created_at": d["created_at"],
    } for d in docs]
    return jsonify({"pending": pending, "count": len(pending)}), 200


@app.route("/api/chat/answer", methods=["GET", "POST"])
def chat_answer():
    """
    AI 写回答案（由运维端 AI 脚本调用）。
    支持 GET（Cloudflare 友好）和 POST 两种方式。

    GET  /api/chat/answer?qid=...&answer=...
    POST /api/chat/answer  Body: {"question_id": "...", "answer": "..."}
    """
    if request.method == "GET":
        qid = (request.args.get("qid") or "").strip()
        answer = (request.args.get("answer") or "").strip()
        analysis = None
    else:
        body = request.get_json(silent=True)
        if not body or not isinstance(body, dict):
            return jsonify({"status": "error", "message": "请求体必须是 JSON 对象"}), 400
        qid = (body.get("question_id") or "").strip()
        answer = (body.get("answer") or "").strip()
        analysis = body.get("analysis")

    if not qid:
        return jsonify({"status": "error", "message": "question_id 必填"}), 400
    if not answer:
        return jsonify({"status": "error", "message": "answer 不能为空"}), 400

    col = _chat_collection()
    result = col.update_one(
        {"question_id": qid, "status": "pending"},
        {"$set": {
            "answer": answer,
            "analysis": analysis,
            "status": "answered",
            "answered_at": datetime.utcnow().isoformat(),
        }},
    )
    if result.matched_count == 0:
        return jsonify({"status": "error", "message": "问题不存在或已处理"}), 404

    logger.info("Chat 答案已写回: qid=%s, len=%d", qid, len(answer))
    return jsonify({"status": "ok", "message": "答案已更新"}), 200


@app.route("/api/records", methods=["GET"])
def query_records():
    """统一查询接口：按用户、设备、时间范围查询 Mongo 或 MySQL。"""
    return _handle_query_request()


@app.route("/api/v1/records", methods=["GET"])
def query_records_v1():
    """兼容文档中的 v1 查询入口。"""
    return _handle_query_request()


@app.route("/api/users/<user_key>/records", methods=["GET"])
def query_records_by_user(user_key: str):
    """按用户查询，user_key 在 Mongo 中按 user_id 匹配，在 MySQL 中可按 user_id 或 username 匹配。"""
    return _handle_query_request(default_user_key=user_key)


@app.route("/api/v1/users/<user_key>/records", methods=["GET"])
def query_records_by_user_v1(user_key: str):
    """兼容文档中的 v1 按用户查询入口。"""
    return _handle_query_request(default_user_key=user_key)


@app.route("/api/devices/<device_key>/records", methods=["GET"])
def query_records_by_device(device_key: str):
    """按设备查询，device_key 在 Mongo 中按 device_id 匹配，在 MySQL 中可按 device_id 或 device_sn 匹配。"""
    return _handle_query_request(default_device_key=device_key)


@app.route("/api/v1/devices/<device_key>/records", methods=["GET"])
def query_records_by_device_v1(device_key: str):
    """兼容文档中的 v1 按设备查询入口。"""
    return _handle_query_request(default_device_key=device_key)


def _build_mongo_profile():
    """从 MongoDB 构建设备档案：结合 user_pets/pets 的绑定信息和 received_records 的最新遥测。"""
    try:
        col = mongo_storage._collection
        db = col.database
        # 最近 500 条遥测中活跃的设备
        pipeline = [
            {"$sort": {"_id": -1}},
            {"$limit": 500},
            {"$group": {
                "_id": "$device_id",
                "count": {"$sum": 1},
                "latest_hr": {"$first": "$heart_rate"},
                "latest_behavior": {"$first": "$behavior"},
                "latest_temp": {"$first": "$temperature"},
                "latest_rr": {"$first": "$resp_rate"},
                "latest_steps": {"$first": "$steps"},
                "latest_battery": {"$first": "$battery"},
                "latest_lat": {"$first": "$gps_lat"},
                "latest_lng": {"$first": "$gps_lng"},
                "latest_ts": {"$first": "$timestamp"},
            }},
            {"$sort": {"count": -1}},
        ]
        active = list(col.aggregate(pipeline))
    except Exception:
        active = []

    # 从 user_pets / pets 获取宠物名和用户绑定
    pet_info = {}
    try:
        for p in db["user_pets"].find({}, {"_id": 0, "device_id": 1, "pet_name": 1, "user_id": 1}):
            pet_info[p["device_id"]] = {"pet_name": p.get("pet_name", ""), "user_id": p.get("user_id", "")}
    except Exception:
        pass
    try:
        for p in db["pets"].find({}, {"_id": 0, "device_id": 1, "pet_name": 1, "user_id": 1}):
            if p["device_id"] not in pet_info:
                pet_info[p["device_id"]] = {"pet_name": p.get("pet_name", ""), "user_id": p.get("user_id", "")}
    except Exception:
        pass

    devices = []
    for d in active:
        did = d["_id"]
        info = pet_info.get(did, {})
        devices.append({
            "device_sn": did,
            "pet_name": info.get("pet_name", ""),
            "user_id": info.get("user_id", ""),
            "is_bound": bool(info.get("user_id")),
            "record_count": d.get("count", 0),
            "latest_heart_rate": d.get("latest_hr"),
            "latest_behavior": d.get("latest_behavior"),
            "latest_temperature": d.get("latest_temp"),
            "latest_resp_rate": d.get("latest_rr"),
            "latest_steps": d.get("latest_steps"),
            "latest_battery": d.get("latest_battery"),
            "latest_gps_lat": d.get("latest_lat"),
            "latest_gps_lng": d.get("latest_lng"),
            "latest_timestamp": str(d.get("latest_ts", ""))[:19],
        })

    return {"devices": devices}


@app.route("/api/profile", methods=["GET"])
def query_profile():
    """查询设备档案信息（支持 Mongo 和 MySQL）。"""
    source = request.args.get("source", "mysql").strip().lower()
    if source == "mongo":
        return _build_query_response("mongo", "profile", _build_mongo_profile())
    return _handle_query_request(source_override="mysql", kind_override="profile")


@app.route("/api/v1/profile", methods=["GET"])
def query_profile_v1():
    """兼容文档中的 v1 profile 入口。"""
    source = request.args.get("source", "mysql").strip().lower()
    if source == "mongo":
        return _build_query_response("mongo", "profile", _build_mongo_profile())
    return _handle_query_request(source_override="mysql", kind_override="profile")


@app.route("/demo/qrcodes")
def demo_qrcodes():
    """动态生成二维码绑定页面，仅显示当前活跃设备（最近 200 条中出现的设备）"""
    try:
        col = mongo_storage._collection
        pipeline = [
            {"$sort": {"_id": -1}},
            {"$limit": 200},
            {"$group": {
                "_id": "$device_id",
                "count": {"$sum": 1},
                "last_hr": {"$first": "$heart_rate"},
                "last_behavior": {"$first": "$behavior"},
                "last_ts": {"$first": "$timestamp"},
            }},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]
        active = list(col.aggregate(pipeline))
    except Exception:
        active = []

    if not active:
        return """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>PetNode 扫码绑定</title><meta http-equiv="refresh" content="10">
<style>body{font-family:-apple-system,sans-serif;background:#f5f5f5;padding:40px;text-align:center}
h1{color:#333}.msg{color:#888;margin-top:20px}</style></head>
<body><h1>PetNode 扫码绑定</h1><p class="msg">暂无活跃设备，请确认 Engine 正在运行。</p>
<p style="color:#aaa;font-size:12px">页面每 10 秒自动刷新</p></body></html>""", 200, {"Content-Type": "text/html; charset=utf-8"}

    # 尝试从 user_pets 获取宠物名称
    pet_names = {}
    try:
        for p in col.database["user_pets"].find({}, {"_id": 0, "device_id": 1, "pet_name": 1}):
            pet_names[p["device_id"]] = p.get("pet_name", "")
    except Exception:
        pass

    emoji = ["🐕", "🐩", "🐕‍🦺", "🦮", "🐶", "🐾", "🦊", "🐺", "🐕", "🐩"]
    cards_html = ""
    for i, d in enumerate(active):
        did = d["_id"]
        name = pet_names.get(did, f"设备 {i+1}")
        hr = d.get("last_hr", "--")
        behavior = d.get("last_behavior", "--")
        ts = (d.get("last_ts") or "")[:19]
        cards_html += f"""<div class="card">
  <h3>{emoji[i % len(emoji)]} {name}</h3>
  <p class="id">{did}</p>
  <img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=petnode:device:{did}" alt="QR">
  <p class="hint"><code>petnode:device:{did}</code></p>
  <p class="hint">❤️ {hr} bpm · {behavior} · {ts}</p>
  <p class="hint">近 5 分钟: {d['count']} 条记录</p>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>PetNode 扫码绑定</title>
<meta http-equiv="refresh" content="30">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,sans-serif;background:#f5f5f5;padding:20px}}
h1{{text-align:center;color:#333;margin-bottom:4px}}
.sub{{text-align:center;color:#888;margin-bottom:20px;font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;max-width:900px;margin:0 auto}}
.card{{background:#fff;border-radius:16px;padding:20px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.05)}}
.card h3{{font-size:16px;margin-bottom:4px}}
.card .id{{font-size:11px;color:#aaa;margin-bottom:10px;word-break:break-all;font-family:monospace}}
.card img{{width:180px;height:180px;border:1px dashed #ddd;border-radius:8px}}
.card .hint{{margin-top:6px;font-size:12px;color:#888}}
.card .hint code{{background:#f0f0f0;padding:2px 6px;border-radius:4px;font-size:11px}}
.steps{{max-width:900px;margin:30px auto;background:#fff;border-radius:16px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,.05)}}
.steps h2{{font-size:18px;margin-bottom:10px}}
.steps ol{{padding-left:20px}}
.steps li{{padding:6px 0;color:#555;line-height:1.6}}
.badge{{display:inline-block;background:#07c160;color:#fff;font-size:10px;padding:2px 8px;border-radius:10px;margin-left:4px}}
</style></head>
<body>
<h1>PetNode 扫码绑定</h1>
<p class="sub">当前活跃设备 · 页面每 30 秒自动刷新</p>
<div class="grid">{cards_html}</div>
<div class="steps">
<h2>操作步骤</h2>
<ol>
<li>微信开发者工具编译小程序</li>
<li>首页点击 <strong>「扫码添加」</strong></li>
<li>扫描上方对应设备的二维码</li>
<li>点击弹窗<strong>「绑定」</strong></li>
<li>新设备出现在首页，点击可查看实时数据</li>
</ol>
</div>
</body></html>""", 200, {"Content-Type": "text/html; charset=utf-8"}




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
