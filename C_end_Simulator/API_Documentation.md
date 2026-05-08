# PetNode Flask & MySQL 接口文档

> **项目名称：** PetNode — 宠物智能项圈数据采集平台  
> **版本：** v2.0（第二阶段验收）  
> **基准提交：** `998d9b7`  
> **最后更新：** 2026-04-16  

---

## 目录

1. [概述](#1-概述)
2. [基础信息](#2-基础信息)
3. [鉴权机制](#3-鉴权机制)
4. [数据完整性保护（HMAC 签名）](#4-数据完整性保护hmac-签名)
5. [数据模型](#5-数据模型)
6. [接口列表](#6-接口列表)
   - 6.1 [上传数据 — POST /api/data](#61-上传数据--post-apidata)
   - 6.2 [健康检查 — GET /api/health](#62-健康检查--get-apihealth)
7. [消息队列通道（RabbitMQ）](#7-消息队列通道rabbitmq)
8. [存储后端](#8-存储后端)
9. [错误码汇总](#9-错误码汇总)
10. [部署与环境变量](#10-部署与环境变量)
11. [请求示例（cURL）](#11-请求示例curl)
12. [Flask & MySQL 接口文档](#12-flask--mysql-接口文档)

---

## 1. 概述

PetNode 后端（S 端）是一个基于 **Flask** 的 RESTful 数据服务器，负责接收由 C 端模拟引擎（Engine）产生的宠物智能项圈数据并持久化存储。

数据上报支持两种通道：

| 通道 | 协议 | 入口 | 说明 |
|------|------|------|------|
| **HTTP API** | HTTP POST | `POST /api/data` | Engine 通过 `HttpExporter` 直接调用 |
| **消息队列** | AMQP (RabbitMQ) | 队列 `petnode.records` | Engine 通过 `MqExporter` 发布消息，`mq-worker` 消费入库 |

两种通道均要求通过 **API Key 鉴权** 和 **HMAC-SHA256 签名验证**。

---

## 2. 基础信息

| 项目 | 值 |
|------|-----|
| Base URL | `http://<服务器IP>:5000` |
| 协议 | HTTP（当前阶段，HTTPS 可选） |
| Content-Type | `application/json; charset=utf-8` |
| 字符编码 | UTF-8 |
| 时间格式 | ISO 8601（`YYYY-MM-DDTHH:MM:SS`） |

---

## 3. 鉴权机制

所有写入接口（`POST /api/data`）和消息队列通道均需通过 **Bearer Token** 鉴权。

### 请求头格式

```
Authorization: Bearer <API_KEY>
```

### 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `API_KEY` | string | 服务端预设密钥，通过环境变量 `API_KEY` 配置，默认值为 `petnode_secret_key_2026` |

### 鉴权失败响应

```json
{
  "status": "error",
  "message": "缺少 Authorization 头"
}
```

或

```json
{
  "status": "error",
  "message": "API Key 无效"
}
```

**HTTP 状态码：** `401 Unauthorized`

---

## 4. 数据完整性保护（HMAC 签名）

在通过 API Key 鉴权之后，服务端还会对请求体进行 **HMAC-SHA256 签名验证**，防止数据在传输过程中被篡改。

### 签名生成流程（客户端）

```
1. 将请求体序列化为 JSON 字符串的原始字节流（UTF-8 编码）
2. 使用 HMAC-SHA256 算法，以 HMAC_KEY 为密钥，对字节流计算摘要
3. 将摘要转为十六进制字符串（hexdigest）
4. 放入请求头 X-Signature
```

**伪代码：**
```python
import hashlib, hmac, json

body_bytes = json.dumps(record).encode("utf-8")
signature = hmac.new(
    HMAC_KEY.encode("utf-8"),
    body_bytes,
    hashlib.sha256
).hexdigest()
```

### 请求头格式

```
X-Signature: <hex_digest>
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `HMAC_KEY` | string | 签名密钥，通过环境变量 `HMAC_KEY` 配置，默认值为 `petnode_hmac_secret_2026` |

### 验签失败响应

```json
{
  "status": "error",
  "message": "缺少 HMAC 签名"
}
```

或

```json
{
  "status": "error",
  "message": "HMAC 签名验证失败，数据可能被篡改"
}
```

**HTTP 状态码：** `403 Forbidden`

> **安全说明：** 服务端使用 `hmac.compare_digest()` 进行常量时间对比，防止��序攻击（timing attack）。

---

## 5. 数据模型

### 项圈数据记录（Record）

Engine 每个 tick 为每只狗生成一条数据记录，结构如下：

| 字段名 | 类型 | 必填 | 示例值 | 说明 |
|--------|------|------|--------|------|
| `device_id` | string | 是 | `"109f156a015a"` | 设备（狗项圈）唯一标识 |
| `timestamp` | string | 是 | `"2025-06-01T00:01:00"` | ISO 8601 格式的模拟时间戳 |
| `behavior` | string | 是 | `"sleeping"` | 行为状态：`sleeping` / `resting` / `walking` / `running` |
| `heart_rate` | float | 是 | `66.2` | 心率（bpm） |
| `resp_rate` | float | 是 | `8.5` | 呼吸频率（次/分钟） |
| `temperature` | float | 是 | `38.45` | 体温（°C） |
| `steps` | int | 是 | `0` | 今日累计步数 |
| `battery` | int | 是 | `100` | 电量百分比 |
| `gps_lat` | float | 是 | `29.57` | GPS 纬度 |
| `gps_lng` | float | 是 | `106.45` | GPS 经度 |
| `event` | string \| null | 是 | `null` 或 `"fever"` | 当前事件名称（无事件时为 `null`） |
| `event_phase` | string \| null | 是 | `null` 或 `"onset"` | 事件阶段：`onset` / `peak` / `recovery`（无事件时为 `null`） |

### 存储附加字段

数据入库时，MongoStorage 会自动追加以下字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `ingested_at` | string | 服务器接收时间（UTC），格式 `"2026-04-16T12:00:00Z"` |
| `_id` | ObjectId | MongoDB 自动生成的文档 ID |

---

## 6. 接口列表

### 6.1 上传数据 — `POST /api/data`

接收一条狗项圈数据记录并持久化到存储层。

#### 请求

| 项目 | 值 |
|------|-----|
| **Method** | `POST` |
| **URL** | `/api/data` |
| **Content-Type** | `application/json` |

#### 请求头

| Header | 必填 | 说明 |
|--------|------|------|
| `Authorization` | ✅ | `Bearer <API_KEY>`，API Key 鉴权 |
| `X-Signature` | ✅ | HMAC-SHA256 签名（hex 字符串），防篡改验签 |
| `Content-Type` | ✅ | `application/json` |

#### 请求体

一个 JSON 对象，字段参见 [5. 数据模型](#5-数据模型)。

```json
{
  "device_id": "109f156a015a",
  "timestamp": "2025-06-01T00:01:00",
  "behavior": "sleeping",
  "heart_rate": 66.2,
  "resp_rate": 8.5,
  "temperature": 38.45,
  "steps": 0,
  "battery": 100,
  "gps_lat": 29.57,
  "gps_lng": 106.45,
  "event": null,
  "event_phase": null
}
```

#### 成功响应

**HTTP 状态码：** `200 OK`

```json
{
  "status": "ok",
  "message": "数据已保存"
}
```

#### 错误响应

| HTTP 状态码 | 触发条件 | 响应体 |
|-------------|---------|--------|
| `400 Bad Request` | 请求体不是合法 JSON 或不是对象 | `{"status": "error", "message": "请求体必须是合法的 JSON 对象"}` |
| `401 Unauthorized` | 缺少 Authorization 头 | `{"status": "error", "message": "缺少 Authorization 头"}` |
| `401 Unauthorized` | API Key 不匹配 | `{"status": "error", "message": "API Key 无效"}` |
| `403 Forbidden` | 缺少 X-Signature 头 | `{"status": "error", "message": "缺少 HMAC 签名"}` |
| `403 Forbidden` | HMAC 签名校验失败 | `{"status": "error", "message": "HMAC 签名验证失败，数据可能被篡改"}` |
| `500 Internal Server Error` | 存储层写入异常 | `{"status": "error", "message": "数据保存失败: <错误详情>"}` |

#### 处理流程

```
客户端请求
    │
    ▼
① API Key 鉴权（Authorization: Bearer <key>）
    │ 失败 → 401
    ▼
② HMAC 签名验证（X-Signature vs 重算签名）
    │ 失败 → 403
    ▼
③ 解析 JSON 请求体
    │ 失败 → 400
    ▼
④ 调用 storage.save(record) 持久化
    │ 失败 → 500
    ▼
⑤ 返回 200 {"status": "ok"}
```

---

### 6.2 健康检查 — `GET /api/health`

用于 Docker 健康检查和运维监控，确认 Flask 服务是否正常运行。

#### 请求

| 项目 | 值 |
|------|-----|
| **Method** | `GET` |
| **URL** | `/api/health` |

> **注意：** 此接口**不需要鉴权**，可直接调用。

#### 成功响应

**HTTP 状态码：** `200 OK`

```json
{
  "status": "healthy",
  "total_received": 123,
  "timestamp": "2026-04-16 14:30:00"
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 固定值 `"healthy"`，表示服务正常 |
| `total_received` | int | 服务启动以来通过 HTTP API 累计接收的数据条数 |
| `timestamp` | string | 当前服务器时间（格式 `YYYY-MM-DD HH:MM:SS`） |

---

## 7. 消息队列通道（RabbitMQ）

除 HTTP API 外，Engine 还可通过 RabbitMQ 消息队列上报数据，由独立的 `mq-worker` 进程消费入库。

### 架构

```
Engine (MqExporter)
    │
    │  AMQP publish
    ▼
┌──────────────────┐
│  RabbitMQ        │
│  Queue:          │
│  petnode.records │
│  (durable)       │
└──────────────────┘
    │
    │  AMQP consume
    ▼
mq-worker
    │
    │  storage.save()
    ▼
MongoDB / FileStorage
```

### 队列配置

| 参数 | 值 |
|------|-----|
| 队列名称 | `petnode.records` |
| 持久化 | `durable=True` |
| Prefetch | `prefetch_count=50` |
| 自动确认 | `auto_ack=False`（手动 ACK） |

### 消息格式

消息体为 JSON 序列化的 Record 字节流（与 HTTP 请求体相同）。

鉴权与签名信息通过 AMQP 消息的 **headers** 属性传递：

| Header Key | 类型 | 说明 |
|------------|------|------|
| `Authorization` | string | `Bearer <API_KEY>` |
| `X-Signature` | string | HMAC-SHA256 签名（对消息体 body 计算） |

### Worker 处理逻辑

| 步骤 | 动作 | 失败处理 |
|------|------|---------|
| ① 鉴权 + 验签 | 校验 headers 中的 Authorization 和 X-Signature | `basic_reject(requeue=False)` — 拒绝毒消息，不重试 |
| ② JSON 解析 | 将 body 反序列化为 dict | `basic_reject(requeue=False)` — 格式错误不重试 |
| ③ 入库 | 调用 `storage.save(record)` | `basic_nack(requeue=True)` — 暂时性故障，消息回队列等待重投递 |
| ④ 确认 | `basic_ack` | — |

### RabbitMQ 管理台

| 项目 | 值 |
|------|-----|
| URL | `http://<服务器IP>:15672` |
| 默认账号 | `guest` / `guest` |

---

## 8. 存储后端

服务端采用**策略模式**，通过环境变量 `STORAGE_BACKEND` 切换存储实现：

### 8.1 MongoStorage（默认）

| 项目 | 值 |
|------|-----|
| 数据库 | MongoDB 7 |
| 数据库名 | `petnode`（环境变量 `MONGO_DB`） |
| 集合名 | `received_records`（环境变量 `MONGO_COLLECTION`） |
| 连接串 | `mongodb://mongodb:27017`（环境变量 `MONGO_URI`） |

**自动创建的索引：**

| 索引 | 字段 | 用途 |
|------|------|------|
| 复合索引 | `(device_id: 1, timestamp: 1)` | 按设备 + 时间范围查询 |

### 8.2 FileStorage（降级 / 本地开发）

| 项目 | 值 |
|------|-----|
| 格式 | JSON Lines（`.jsonl`，每行一条 JSON） |
| 文件路径 | `/app/data/received.jsonl` |
| 写入保证 | 每条记录写入后调用 `flush()` + `os.fsync()` |
| 线程安全 | 使用 `threading.Lock` 保护 |

---

## 9. 错误码汇总

| HTTP 状态码 | 含义 | 触发场景 |
|-------------|------|---------|
| `200` | 成功 | 数据保存成功 / 健康检查正常 |
| `400` | 请求错误 | 请求体非合法 JSON 对象 |
| `401` | 未授权 | 缺少或无效的 API Key |
| `403` | 禁止访问 | 缺少或无效的 HMAC 签名 |
| `500` | 服务器内部错误 | 存储层写入异常（MongoDB / 文件写入失败） |

---

## 10. 部署与环境变量

### Flask Server（`petnode-flask`）

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `STORAGE_BACKEND` | `mongo` | 存储后端：`mongo` 或 `file` |
| `PORT` | `5000` | Flask 监听端口 |
| `API_KEY` | `petnode_secret_key_2026` | API Key 鉴权密钥 |
| `HMAC_KEY` | `petnode_hmac_secret_2026` | HMAC 签名密钥 |
| `MONGO_URI` | `mongodb://mongodb:27017` | MongoDB 连接串 |
| `MONGO_DB` | `petnode` | MongoDB 数据库名 |
| `MONGO_COLLECTION` | `received_records` | MongoDB 集合名 |
| `DATA_DIR` | `/app/data` | FileStorage 数据目录（仅 `file` 模式） |

### MQ Worker（`petnode-mq-worker`）

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/` | RabbitMQ 连接串 |
| `RABBITMQ_QUEUE` | `petnode.records` | 消费队列名 |
| `API_KEY` | `petnode_secret_key_2026` | 与 Engine / Flask 一致 |
| `HMAC_KEY` | `petnode_hmac_secret_2026` | 与 Engine / Flask 一致 |
| `STORAGE_BACKEND` | `mongo` | 存储后端（与 Flask 一致） |
| `MONGO_URI` / `MONGO_DB` / `MONGO_COLLECTION` | 同上 | MongoDB 配置 |

### Docker Compose 服务编排

```
┌─────────────┐    healthcheck     ┌──────────────┐
│  MongoDB    │◄───────────────────│  Flask Server│ :5000
│  :27017     │                    └──────┬───────┘
└──────┬──────┘                           │
       │                                  │ depends_on
       │         ┌──────────────┐         │
       ├────────►│  MQ Worker   │◄────────┘
       │         └──────┬───────┘
       │                │
       │         ┌──────┴───────┐
       │         │  RabbitMQ    │ :5672 / :15672
       │         └──────┬───────┘
       │                │
       │         ┌──────┴───────┐
       └─────────│   Engine     │──► output_data/
                 └──────────────┘
```

启动命令：
```bash
docker compose up -d                          # 启动所有后台服务
docker compose --profile tui run --rm tui     # 交互式启动 TUI 监控
docker compose down                           # 停止所有服务
```

---

## 11. 请求示例（cURL）

### 上传数据

```bash
# 1. 构造请求体
BODY='{"device_id":"109f156a015a","timestamp":"2025-06-01T00:01:00","behavior":"sleeping","heart_rate":66.2,"resp_rate":8.5,"temperature":38.45,"steps":0,"battery":100,"gps_lat":29.57,"gps_lng":106.45,"event":null,"event_phase":null}'

# 2. 计算 HMAC-SHA256 签名
SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "petnode_hmac_secret_2026" | awk '{print $2}')

# 3. 发送请求
curl -X POST http://localhost:5000/api/data \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer petnode_secret_key_2026" \
  -H "X-Signature: $SIGNATURE" \
  -d "$BODY"
```

**预期响应：**
```json
{"status": "ok", "message": "数据已保存"}
```

### 健康检查

```bash
curl http://localhost:5000/api/health
```

**预期响应：**
```json
{"status": "healthy", "total_received": 0, "timestamp": "2026-04-16 14:30:00"}
```

---

## 12. Flask & MySQL 接口文档

> **范围：** `C_end_Simulator/flask_server`  
> **说明：** 以下内容按微信端联调与后端 MySQL 内部查询整理；当前仓库里已实现的 Flask 路由主要是 `/api/data`、`/api/health`、`/api/records`、`/api/users/<user_key>/records`、`/api/devices/<device_key>/records` 和 `/api/profile`，其余条目按接口约定保留。

### 表 1：总览（先列举）

| 模块 | 方法 | 路径/函数 | 用途 |
|---|---|---|---|
| 微信登录 | POST | `/api/v1/wechat/auth` | code 换微信身份票据，已绑定则直接回 access_token |
| 微信绑定 | POST | `/api/v1/wechat/bind` | 微信身份绑定系统用户 |
| 微信解绑 | POST | `/api/v1/wechat/unbind` | 解除微信绑定 |
| 用户信息 | GET | `/api/v1/me` | 查询当前用户资料与自有宠物 |
| 用户信息 | PUT | `/api/v1/me` | 修改 `nickname/avatar_url` |
| 设备绑定 | POST | `/api/v1/devices/bind` | 认领项圈并建立宠物档案 |
| 设备解绑 | POST | `/api/v1/devices/{device_id}/unbind` | 解除设备绑定 |
| 宠物列表 | GET | `/api/v1/pets` | 查询用户可访问宠物（本人+家庭共享） |
| 宠物概览 | GET | `/api/v1/pets/{pet_id}/summary` | 首页概览数据 |
| 呼吸最新 | GET | `/api/v1/pets/{pet_id}/respiration/latest` | 最新呼吸频率 |
| 呼吸序列 | GET | `/api/v1/pets/{pet_id}/respiration/series` | 呼吸曲线 |
| 心率最新 | GET | `/api/v1/pets/{pet_id}/heart-rate/latest` | 最新心率 |
| 心率序列 | GET | `/api/v1/pets/{pet_id}/heart-rate/series` | 心率曲线 |
| 体温序列 | GET | `/api/v1/pets/{pet_id}/temperature/series` | 体温曲线 |
| 最新定位 | GET | `/api/v1/pets/{pet_id}/location/latest` | 最新 GPS |
| 事件列表 | GET | `/api/v1/pets/{pet_id}/events` | 告警事件分页列表 |
| 事件已读 | PUT | `/api/v1/pets/{pet_id}/events/{event_id}/read` | 告警红点消除 |
| 宠物资料 | PUT | `/api/v1/pets/{pet_id}` | 修改宠物档案 |
| 家庭组 | POST | `/api/v1/family` | 创建家庭组 |
| 家庭组 | POST | `/api/v1/family/invite` | 生成邀请码 |
| 家庭组 | POST | `/api/v1/family/join` | 扫码加入家庭 |
| 家庭组 | GET | `/api/v1/family/members` | 查询家庭成员 |
| 家庭组 | DELETE | `/api/v1/family/members/{user_id}` | 踢人/主动退出 |
| MySQL 内部 | 方法 | `MySQLStorage.save(record)` | 写入异常记录（anomaly） |
| MySQL 内部 | 方法 | `MySQLStorage.query_anomalies(...)` | 按条件查询异常列表 |
| MySQL 内部 | 方法 | `MySQLStorage.query_profile(...)` | 查询 user/device/trait/event 档案 |
| MySQL 内部 | 方法 | `MySQLStorage._resolve_user_id_from_record(record, now)` | 从每条 JSON 解析并落 user_id |
| MySQL 内部 | 方法 | `MySQLStorage._ensure_device(device_sn, now, user_id)` | 设备 upsert 并绑定 user_id |

### 表 2：逐项说明（详细参数）

| 名称 | 关键入参 | 关键返回 | 说明 |
|---|---|---|---|
| `/api/v1/devices/bind` | `device_id?`, `pet_name`, `breed`, `avatar_url`, `weight` | `pet_id`, `device_id`, `bind_status` | `device_id` 可空（后端按未认领设备稳定分配）；设备全局唯一认领，不允许重复跨用户绑定 |
| `/api/v1/devices/{device_id}/unbind` | 路径 `device_id` | `unbind_status` | 解除后该用户不再接收该设备数据权限 |
| `/api/v1/family` | 无 | `family_id` | Owner 创建家庭组（幂等） |
| `/api/v1/family/invite` | `expires_in?` | `invite_token`, `expires_in` | 生成有时效的邀请码 |
| `/api/v1/family/join` | `invite_token` | `join_status`, `family_id` | 家人扫码加入，权限写入家庭成员表 |
| `/api/v1/family/members` | 无 | `members[{user_id,nickname,role}]` | 查询当前用户所在家庭成员 |
| `/api/v1/family/members/{user_id}` | 路径 `user_id` | `status=removed` | Owner 可踢人；成员可删除自己（退出） |
| `/api/v1/me (PUT)` | `nickname`, `avatar_url` | `user_id`, `nickname`, `avatar_url` | 用户资料修改 |
| `/api/v1/pets/{pet_id} (PUT)` | `pet_name`, `avatar_url`, `weight`, `breed` | 更新后的宠物资料 | 仅设备 owner 可修改 |
| `/api/v1/pets/{pet_id}/temperature/series` | `start?`, `end?`, `limit?` | `points[{ts,value_celsius}]` | 独立体温曲线接口 |
| `/api/v1/pets/{pet_id}/location/latest` | 无 | `lat`, `lng`, `ts` | 最新定位快照 |
| `/api/v1/pets/{pet_id}/events/{event_id}/read` | 路径 `event_id` | `status=marked_read` | 标记告警已读，支持前端红点消除 |
| `/api/v1/pets` | 无 | `pets[]` | 返回本人绑定 + 家庭共享可访问宠物 |
| `MySQLStorage._resolve_user_id_from_record` | `record.user_id?` | 解析后的 `user_id` | 已检查：每条 JSON 在入 MySQL 前都会解析并确保 `user` 表存在对应行 |
| `MySQLStorage.save` | 扁平 JSON 记录 | 无（内部写库） | 当前落 `anomaly_record`，并串联事件实例状态 |
| `MySQLStorage.query_anomalies` | `user_key/device_key/start/end/limit/offset` | 异常记录列表 | VX 或内部工具按用户/设备查异常 |
| `MySQLStorage.query_profile` | `user_key?`, `device_key?` | `users/devices/traits/events` | 联调用的静态档案查询 |

---

> **文档生成自：** 代码版本 `998d9b7` @ `BassttElSevic/PetNode`