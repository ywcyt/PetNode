# PetNode 后端接口文档

> **项目名称：** PetNode — 宠物智能项圈数据采集平台  
> **版本：** v3.0（vx 微信端集成）  
> **最后更新：** 2026-05-03  

---

## 目录

1. [概述](#1-概述)
2. [基础信息](#2-基础信息)
3. [鉴权机制](#3-鉴权机制)
   - 3.1 [Engine → Flask：API Key + HMAC 签名](#31-engine--flask-api-key--hmac-签名)
   - 3.2 [vx → Flask：JWT Bearer Token](#32-vx--flask-jwt-bearer-token)
4. [数据完整性保护（HMAC 签名）](#4-数据完整性保护hmac-签名)
5. [数据模型](#5-数据模型)
6. [接口列表 — Engine 数据上报（原有）](#6-接口列表--engine-数据上报原有)
   - 6.1 [上传数据 — POST /api/data](#61-上传数据--post-apidata)
   - 6.2 [健康检查 — GET /api/health](#62-健康检查--get-apihealth)
7. [接口列表 — vx 微信端（新增）](#7-接口列表--vx-微信端新增)
   - 7.1 [微信身份校验 — POST /api/v1/wechat/auth](#71-微信身份校验--post-apiv1wechatauth)
   - 7.2 [绑定微信账号 — POST /api/v1/wechat/bind](#72-绑定微信账号--post-apiv1wechatbind)
   - 7.3 [解绑微信账号 — POST /api/v1/wechat/unbind](#73-解绑微信账号--post-apiv1wechatunbind)
   - 7.4 [当前用户信息 — GET /api/v1/me](#75-当前用户信息--get-apiv1me)
   - 7.5 [宠物状态快照 — GET /api/v1/pets/{pet_id}/summary](#76-宠物状态快照--get-apiv1petspet_idsummary)
   - 7.6 [最新呼吸采样 — GET /api/v1/pets/{pet_id}/respiration/latest](#77-最新呼吸采样--get-apiv1petspet_idrespirationlatest)
   - 7.7 [呼吸频率序列 — GET /api/v1/pets/{pet_id}/respiration/series](#78-呼吸频率序列--get-apiv1petspet_idrespirationseries)
   - 7.8 [最新心率采样 — GET /api/v1/pets/{pet_id}/heart-rate/latest](#79-最新心率采样--get-apiv1petspet_idheart-ratelatest)
   - 7.9 [心率序列 — GET /api/v1/pets/{pet_id}/heart-rate/series](#710-心率序列--get-apiv1petspet_idheart-rateseries)
   - 7.10 [事件列表 — GET /api/v1/pets/{pet_id}/events](#711-事件列表--get-apiv1petspet_idevents)
8. [内部函数说明](#8-内部函数说明)
8. [内部函数说明](#8-内部函数说明)
9. [消息队列通道（RabbitMQ）](#9-消息队列通道rabbitmq)
10. [存储后端](#10-存储后端)
11. [错误码汇总](#11-错误码汇总)
12. [部署与环境变量](#12-部署与环境变量)
13. [请求示例（cURL）](#13-请求示例curl)
14. [vx 端集成指南](#14-vx-端集成指南)

---

## 1. 概述

PetNode 后端（S 端）是一个基于 **Flask** 的 RESTful 数据服务器，负责接收由 C 端模拟引擎（Engine）产生的宠物智能项圈数据并持久化存储。

数据上报支持两种通道：

| 通道 | 协议 | 入口 | 调用方 | 说明 |
|------|------|------|--------|------|
| **HTTP API** | HTTP POST | `POST /api/data` | Engine | Engine 通过 `HttpExporter` 直接调用 |
| **消息队列** | AMQP (RabbitMQ) | 队列 `petnode.records` | Engine | Engine 通过 `MqExporter` 发布消息，`mq-worker` 消费入库 |
| **vx API** | HTTP REST | `/api/v1/*` | 微信小程序 | vx 端调用 Flask 进行登录、绑定、查询宠物遥测数据 |

Engine 上报通道要求 **API Key 鉴权** 和 **HMAC-SHA256 签名验证**。  
vx API 通道要求 **JWT Bearer Token 鉴权**（通过 `/wechat/auth` + `/wechat/bind` 流程获取）。

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

### 3.1 Engine → Flask：API Key + HMAC 签名

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

### 3.2 vx → Flask：JWT Bearer Token

vx API（`/api/v1/*`）使用 **JWT（JSON Web Token）** 进行鉴权。

#### Token 获取流程

1. vx 调用 `wx.login()` 获取临时 `code`
2. 调用 `POST /api/v1/wechat/auth`，传入 `code`
3. 若已绑定：响应中直接返回 `access_token`
4. 若未绑定：调用 `POST /api/v1/wechat/bind`，传入 `wx_identity_token`，返回 `access_token`

#### 请求头格式

```
Authorization: Bearer <access_token>
```

#### Token 说明

| Token 类型 | 有效期 | 用途 |
|------------|--------|------|
| `access_token` | 7 天 | 访问所有 vx API（`/me`、`/pets/*`） |
| `wx_identity_token` | 10 分钟 | 仅用于 `/wechat/bind` 步骤，不可用于其他接口 |

#### Token 过期处理

vx 端收到 `401` 响应且 `code == 40101` 时，应触发重新登录流程（重新调用 `wx.login()` + `/wechat/auth`）。

#### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `JWT_SECRET` | `petnode_jwt_secret_2026` | JWT 签名密钥（生产环境务必修改） |

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

Engine 每个 tick 为每只狗生成一条数据记录；**记录本身不包含 `user_id`，只包含 `device_id`**，用户绑定关系应由服务端绑定域单独维护。

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

### vx API 相关集合（MongoDB）

| 集合名 | 说明 | 关键字段 |
|--------|------|----------|
| `users` | 系统用户 | `user_id`（UUID）、`nickname`、`created_at` |
| `wechat_bindings` | 微信身份与系统用户的绑定关系 | `user_id`、`openid`、`unionid`（可选）、`bound_at` |
| `user_pets` | 用户与设备（宠物）的关联 | `user_id`、`device_id`、`pet_name`、`added_at` |
| `received_records` | 项圈遥测数据（同上，Engine 写入） | `device_id`、`timestamp`、`heart_rate`、`resp_rate`、`event` |

> **注意：** `pet_id`（vx API 路径参数）与 `device_id`（遥测数据字段）是同一个值，均为设备唯一标识。

---

## 6. 接口列表 — Engine 数据上报（原有）

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

一个 JSON 对象，字段参见 [5. 数据模型](#5-数据模型)。当前 Engine 上传的请求体**不包含 `user_id`**。

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

## 7. 接口列表 — vx 微信端（新增）

### 统一响应格式

所有 vx API（`/api/v1/*`）使用统一 envelope：

```json
{
  "code": 0,
  "message": "ok",
  "data": { ... },
  "server_time": "2026-05-03T12:00:00+00:00"
}
```

失败时：

```json
{
  "code": 40101,
  "message": "未授权，请先登录",
  "data": null,
  "server_time": "2026-05-03T12:00:00+00:00"
}
```

### 接口总览

| 方法 | 路径 | 用途 | 需要 Auth |
|------|------|------|-----------|
| POST | `/api/v1/wechat/auth` | 微信身份校验（code → wx_identity_token） | ❌ |
| POST | `/api/v1/wechat/bind` | 绑定微信与系统账号 | 可选（有则绑定已有账号，无则新建） |
| POST | `/api/v1/wechat/unbind` | 解除当前用户的微信绑定 | ✅ |
| GET | `/api/v1/me` | 获取当前用户信息与宠物列表 | ✅ |
| GET | `/api/v1/pets/{pet_id}/summary` | 宠物最新状态快照 | ✅ |
| GET | `/api/v1/pets/{pet_id}/respiration/latest` | 最新呼吸频率采样 | ✅ |
| GET | `/api/v1/pets/{pet_id}/respiration/series` | 呼吸频率时间序列 | ✅ |
| GET | `/api/v1/pets/{pet_id}/heart-rate/latest` | 最新心率采样 | ✅ |
| GET | `/api/v1/pets/{pet_id}/heart-rate/series` | 心率时间序列 | ✅ |
| GET | `/api/v1/pets/{pet_id}/events` | 事件列表（支持分页） | ✅ |

---

### 7.1 微信身份校验 — `POST /api/v1/wechat/auth`

vx 端通过 `wx.login()` 获取临时 `code` 后，调用此接口换取微信身份票据。

#### 请求

| 项目 | 值 |
|------|-----|
| **Method** | `POST` |
| **URL** | `/api/v1/wechat/auth` |
| **Content-Type** | `application/json` |
| **Auth** | 不需要 |

#### 请求体

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | ✅ | `wx.login()` 返回的临时登录凭证 |

```json
{
  "code": "wx_temp_code_from_wx_login"
}
```

#### 成功响应（未绑定）

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "is_bound": false,
    "wx_identity_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  },
  "server_time": "2026-05-03T12:00:00+00:00"
}
```

#### 成功响应（已绑定）

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "is_bound": true,
    "wx_identity_token": "eyJ...",
    "access_token": "eyJ...",
    "user_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "server_time": "2026-05-03T12:00:00+00:00"
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_bound` | bool | 该微信身份是否已绑定系统账号 |
| `wx_identity_token` | string | 10 分钟有效的微信身份票据，用于 `/wechat/bind` |
| `access_token` | string | 仅 `is_bound=true` 时返回，7 天有效 |
| `user_id` | string | 仅 `is_bound=true` 时返回 |

#### 错误响应

| code | HTTP | 说明 |
|------|------|------|
| `42201` | 422 | `code` 参数为空 |
| `40102` | 400 | 微信 code 无效或已过期 |
| `50001` | 502 | 微信服务器请求超时 |

---

### 7.2 绑定微信账号 — `POST /api/v1/wechat/bind`

将微信身份与系统用户绑定。若不携带 `Authorization`，自动创建新用户。

#### 请求

| 项目 | 值 |
|------|-----|
| **Method** | `POST` |
| **URL** | `/api/v1/wechat/bind` |
| **Content-Type** | `application/json` |
| **Auth** | 可选（见下） |

#### 请求头（可选）

| Header | 说明 |
|--------|------|
| `Authorization: Bearer <access_token>` | 已有账号时携带，将微信绑定到该账号；不携带则新建用户 |

#### 请求体

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `wx_identity_token` | string | ✅ | 由 `/wechat/auth` 返回的 10 分钟票据 |

```json
{
  "wx_identity_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### 成功响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "bind_status": "bound",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "bound_at": "2026-05-03T12:00:00+00:00",
    "access_token": "eyJ..."
  },
  "server_time": "2026-05-03T12:00:00+00:00"
}
```

若微信已绑定（幂等调用）：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "bind_status": "already_bound",
    "user_id": "550e8400-...",
    "bound_at": "2026-05-03T12:00:00+00:00"
  },
  "server_time": "..."
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `bind_status` | string | `"bound"` 新绑定 / `"already_bound"` 已绑定 |
| `user_id` | string | 系统用户 ID |
| `bound_at` | string | 绑定时间（ISO 8601） |
| `access_token` | string | 新绑定时返回，7 天有效 |

#### 错误响应

| code | HTTP | 说明 |
|------|------|------|
| `42201` | 422 | `wx_identity_token` 参数为空 |
| `40103` | 401 | `wx_identity_token` 无效或已过期 |
| `40101` | 401 | `Authorization` 中的 `access_token` 无效 |
| `40901` | 409 | 该微信已绑定其他系统账号 |

---

### 7.3 解绑微信账号 — `POST /api/v1/wechat/unbind`

解除当前登录用户的微信绑定关系。若当前用户未绑定微信，幂等返回 `not_bound`。

#### 请求

| 项目 | 值 |
|------|-----|
| **Method** | `POST` |
| **URL** | `/api/v1/wechat/unbind` |
| **Auth** | ✅ Bearer access_token（必填） |

#### 成功响应（已绑定且成功解绑）

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "unbind_status": "unbound",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "unbound_at": "2026-05-03T12:00:00+00:00"
  },
  "server_time": "2026-05-03T12:00:00+00:00"
}
```

#### 成功响应（未曾绑定）

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "unbind_status": "not_bound",
    "user_id": "550e8400-...",
    "unbound_at": null
  },
  "server_time": "..."
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `unbind_status` | string | `"unbound"` 解绑成功 / `"not_bound"` 原本未绑定 |
| `user_id` | string | 系统用户 ID |
| `unbound_at` | string\|null | 解绑时间（ISO 8601）；`not_bound` 时为 null |

#### 错误响应

| code | HTTP | 说明 |
|------|------|------|
| `40101` | 401 | Token 无效或未携带 |

---

### 7.5 当前用户信息 — `GET /api/v1/me`

返回当前登录用户的基础信息及其关联宠物列表。

#### 请求

| 项目 | 值 |
|------|-----|
| **Method** | `GET` |
| **URL** | `/api/v1/me` |
| **Auth** | ✅ Bearer access_token |

#### 成功响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "nickname": "旺财主人",
    "created_at": "2026-05-01T09:00:00+00:00",
    "pets": [
      { "device_id": "109f156a015a", "pet_name": "旺财" }
    ]
  },
  "server_time": "2026-05-03T12:00:00+00:00"
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_id` | string | 系统用户 UUID |
| `nickname` | string\|null | 用户昵称（暂未自动从微信获取，可手动写入 `users` 集合） |
| `created_at` | string\|null | 账号创建时间 |
| `pets` | list | 已注册宠物列表，每项含 `device_id`、`pet_name` |

#### 错误响应

| code | HTTP | 说明 |
|------|------|------|
| `40101` | 401 | Token 无效或未携带 |

> **如何注册宠物？**  
> 目前需直接向 MongoDB `user_pets` 集合插入：  
> `{ "user_id": "<your_user_id>", "device_id": "109f156a015a", "pet_name": "旺财", "added_at": "2026-05-01T00:00:00" }`

---

### 7.6 宠物状态快照 — `GET /api/v1/pets/{pet_id}/summary`

一次性获取宠物最新状态、呼吸频率、心率、当前事件。

#### 请求

| 项目 | 值 |
|------|-----|
| **Method** | `GET` |
| **URL** | `/api/v1/pets/{pet_id}/summary` |
| **路径参数** | `pet_id` — 设备 ID（与 `device_id` 相同） |
| **Auth** | ✅ Bearer access_token |

#### 成功响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "pet_id": "109f156a015a",
    "dog_status": "resting",
    "latest_respiration_bpm": 18.5,
    "latest_heart_rate_bpm": 72.3,
    "current_event": "fever",
    "current_event_phase": "onset",
    "last_reported_at": "2026-05-03T11:59:00"
  },
  "server_time": "2026-05-03T12:00:00+00:00"
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `pet_id` | string | 设备 ID |
| `dog_status` | string | 行为状态：`sleeping` / `resting` / `walking` / `running` |
| `latest_respiration_bpm` | float | 最新呼吸频率（次/分钟） |
| `latest_heart_rate_bpm` | float | 最新心率（bpm） |
| `current_event` | string\|null | 当前事件名称（无事件为 `null`）。已知值：`fever`、`injury` |
| `current_event_phase` | string\|null | 事件阶段：`onset` / `peak` / `recovery`（无事件为 `null`） |
| `last_reported_at` | string | 最新数据上报时间（ISO 8601） |

#### 错误响应

| code | HTTP | 说明 |
|------|------|------|
| `40301` | 403 | 无权访问该宠物（未在 `user_pets` 中注册） |
| `40401` | 404 | 宠物不存在或暂无上报数据 |

---

### 7.7 最新呼吸采样 — `GET /api/v1/pets/{pet_id}/respiration/latest`

返回最新一条呼吸频率采样（单点，适合首页轻量刷新）。

#### 请求

| 项目 | 值 |
|------|-----|
| **Method** | `GET` |
| **URL** | `/api/v1/pets/{pet_id}/respiration/latest` |
| **Auth** | ✅ Bearer access_token |

#### 成功响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "pet_id": "109f156a015a",
    "unit": "bpm",
    "value_bpm": 18.5,
    "ts": "2026-05-03T11:59:00"
  },
  "server_time": "2026-05-03T12:00:00+00:00"
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `unit` | string | 固定值 `"bpm"`（次/分钟） |
| `value_bpm` | float | 最新呼吸频率值 |
| `ts` | string | 采样时间（ISO 8601） |

---

### 7.8 呼吸频率序列 — `GET /api/v1/pets/{pet_id}/respiration/series`

返回一段时间内的呼吸频率时间序列（用于折线图）。

#### 请求

| 项目 | 值 |
|------|-----|
| **Method** | `GET` |
| **URL** | `/api/v1/pets/{pet_id}/respiration/series` |
| **Auth** | ✅ Bearer access_token |

#### 查询参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `start` | string | ❌ | — | 起始时间（ISO 8601），如 `2026-05-03T00:00:00` |
| `end` | string | ❌ | — | 结束时间（ISO 8601） |
| `limit` | int | ❌ | `50` | 返回条数上限（最大 `500`） |

#### 成功响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "pet_id": "109f156a015a",
    "unit": "bpm",
    "count": 3,
    "points": [
      { "ts": "2026-05-03T10:00:00", "value_bpm": 17.2 },
      { "ts": "2026-05-03T10:01:00", "value_bpm": 18.5 },
      { "ts": "2026-05-03T10:02:00", "value_bpm": 19.1 }
    ]
  },
  "server_time": "2026-05-03T12:00:00+00:00"
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `count` | int | 实际返回的数据点数 |
| `points` | list | 时间序列点，每项含 `ts`（ISO 8601）和 `value_bpm`（float） |

#### 错误响应

| code | HTTP | 说明 |
|------|------|------|
| `42201` | 422 | `limit` 不是整数 |
| `40301` | 403 | 无权访问 |

---

### 7.9 最新心率采样 — `GET /api/v1/pets/{pet_id}/heart-rate/latest`

返回最新一条心率采样（单点）。

#### 请求

| 项目 | 值 |
|------|-----|
| **Method** | `GET` |
| **URL** | `/api/v1/pets/{pet_id}/heart-rate/latest` |
| **Auth** | ✅ Bearer access_token |

#### 成功响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "pet_id": "109f156a015a",
    "unit": "bpm",
    "value_bpm": 72.3,
    "ts": "2026-05-03T11:59:00"
  },
  "server_time": "2026-05-03T12:00:00+00:00"
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `unit` | string | 固定值 `"bpm"` |
| `value_bpm` | float | 最新心率值 |
| `ts` | string | 采样时间（ISO 8601） |

---

### 7.10 心率序列 — `GET /api/v1/pets/{pet_id}/heart-rate/series`

返回一段时间内的心率时间序列（用于折线图）。

#### 请求

| 项目 | 值 |
|------|-----|
| **Method** | `GET` |
| **URL** | `/api/v1/pets/{pet_id}/heart-rate/series` |
| **Auth** | ✅ Bearer access_token |

#### 查询参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `start` | string | ❌ | — | 起始时间（ISO 8601） |
| `end` | string | ❌ | — | 结束时间（ISO 8601） |
| `limit` | int | ❌ | `50` | 返回条数上限（最大 `500`） |

#### 成功响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "pet_id": "109f156a015a",
    "unit": "bpm",
    "count": 3,
    "points": [
      { "ts": "2026-05-03T10:00:00", "value_bpm": 70.5 },
      { "ts": "2026-05-03T10:01:00", "value_bpm": 72.3 },
      { "ts": "2026-05-03T10:02:00", "value_bpm": 74.0 }
    ]
  },
  "server_time": "2026-05-03T12:00:00+00:00"
}
```

---

### 7.11 事件列表 — `GET /api/v1/pets/{pet_id}/events`

返回宠物的事件/告警记录，支持 cursor 分页、时间过滤、事件类型过滤。

#### 请求

| 项目 | 值 |
|------|-----|
| **Method** | `GET` |
| **URL** | `/api/v1/pets/{pet_id}/events` |
| **Auth** | ✅ Bearer access_token |

#### 查询参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `start` | string | ❌ | — | 起始时间（ISO 8601） |
| `end` | string | ❌ | — | 结束时间（ISO 8601） |
| `event_type` | string | ❌ | — | 过滤事件类型（如 `fever`、`injury`） |
| `cursor` | string | ❌ | — | 分页游标（上次响应的 `next_cursor`） |
| `limit` | int | ❌ | `20` | 每页条数（最大 `100`） |

#### 成功响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "pet_id": "109f156a015a",
    "items": [
      {
        "ts": "2026-05-03T10:05:00",
        "type": "fever",
        "phase": "onset",
        "behavior": "resting"
      },
      {
        "ts": "2026-05-02T15:30:00",
        "type": "injury",
        "phase": "peak",
        "behavior": "walking"
      }
    ],
    "next_cursor": "2026-05-02T15:30:00"
  },
  "server_time": "2026-05-03T12:00:00+00:00"
}
```

#### 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `items` | list | 事件列表，按时间倒序排列 |
| `items[].ts` | string | 事件时间（ISO 8601） |
| `items[].type` | string | 事件类型（`fever` / `injury` / 其他自定义） |
| `items[].phase` | string\|null | 事件阶段（`onset` / `peak` / `recovery`） |
| `items[].behavior` | string | 事件发生时的行为状态 |
| `next_cursor` | string\|null | 下一页游标（无更多数据时为 `null`） |

#### 分页使用方式

```
首次请求: GET /api/v1/pets/xxx/events?limit=20
→ 若 next_cursor 非 null，翻页：
GET /api/v1/pets/xxx/events?cursor=<next_cursor>&limit=20
```

---

## 8. 内部函数说明

Flask 服务层（`flask_server/services/`）包含以下内部函数组，供路由层调用（不暴露为独立 HTTP 接口）：

| 模块 | 函数分组 | 主要函数 |
|------|----------|----------|
| `services/identity.py` | 用户身份哈希工具 | `normalize_identity()` / `build_user_hash()` / `get_or_create_user_hash()` |
| `services/binding.py` | 绑定/解绑服务 | `bind_user_to_wechat()` / `unbind_user_from_wechat()` / `bind_user_to_device()` / `unbind_user_from_device()` / `assert_user_owns_pet()` |
| `services/telemetry.py` | 遥测数据查询 | `get_pet_summary()` / `get_latest_respiration()` / `get_respiration_series()` / `get_latest_heart_rate()` / `get_heart_rate_series()` / `list_pet_events()` |

> **详细文档（函数签名、输入输出字段、异常说明）请参见：**  
> [`docs/internal-functions.md`](docs/internal-functions.md)

---

## 9. 消息队列通道（RabbitMQ）

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

## 10. 存储后端

服务端采用**策略模式**，通过环境变量 `STORAGE_BACKEND` 切换存储实现：

### 9.1 MongoStorage（默认）

| 项目 | 值 |
|------|-----|
| 数据库 | MongoDB 7 |
| 数据库名 | `petnode`（环境变量 `MONGO_DB`） |
| 集合名 | `received_records`（环境变量 `MONGO_COLLECTION`） |
| 连接串 | `mongodb://mongodb:27017`（环境变量 `MONGO_URI`） |

**自动创建的索引：**

| 索引 | 字段 | 用途 |
|------|------|------|
| 复合索引 | `(device_id, timestamp)` | Engine 写入数据后按设备 + 时间范围查询 |
| 复合索引（降序） | `(device_id, timestamp DESC)` | vx API 快速取最新记录 |
| 唯一索引 | `wechat_bindings.openid` | 防止重复绑定 |
| 稀疏唯一索引 | `wechat_bindings.unionid` | 优先用 unionid 去重（可选） |
| 复合唯一索引 | `user_pets.(user_id, device_id)` | 防止重复注册宠物 |

### 9.2 FileStorage（降级 / 本地开发）

| 项目 | 值 |
|------|-----|
| 格式 | JSON Lines（`.jsonl`，每行一条 JSON） |
| 文件路径 | `/app/data/received.jsonl` |
| 写入保证 | 每条记录写入后调用 `flush()` + `os.fsync()` |
| 线程安全 | 使用 `threading.Lock` 保护 |

---

## 11. 错误码汇总

### Engine 上报通道

| HTTP 状态码 | 含义 | 触发场景 |
|-------------|------|---------|
| `200` | 成功 | 数据保存成功 / 健康检查正常 |
| `400` | 请求错误 | 请求体非合法 JSON 对象 |
| `401` | 未授权 | 缺少或无效的 API Key |
| `403` | 禁止访问 | 缺少或无效的 HMAC 签名 |
| `500` | 服务器内部错误 | 存储层写入异常（MongoDB / 文件写入失败） |

### vx API 通道（业务错误码）

| 业务 code | HTTP | 含义 | 触发场景 |
|-----------|------|------|---------|
| `0` | 200 | 成功 | 请求处理正常 |
| `40101` | 401 | Token 无效/过期 | access_token 缺失、格式错误、过期 |
| `40102` | 400 | 微信 code 无效 | code 不存在、已使用、过期 |
| `40103` | 401 | wx_identity_token 无效/过期 | 10 分钟票据已失效，需重新调用 `/wechat/auth` |
| `40301` | 403 | 无宠物访问权限 | `user_pets` 中未注册该 `device_id` |
| `40401` | 404 | 资源不存在 | 宠物不存在或暂无数据 |
| `40901` | 409 | 绑定冲突 | 微信身份已绑定其他账号，或并发绑定冲突 |
| `42201` | 422 | 参数错误 | 必填参数为空、格式错误（如 limit 非整数） |
| `50001` | 502 | 微信服务超时 | 调用微信 code2Session 接口超时 |

---

## 12. 部署与环境变量

### Flask Server（`petnode-flask`）

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `STORAGE_BACKEND` | `mongo` | 存储后端：`mongo` 或 `file` |
| `PORT` | `5000` | Flask 监听端口 |
| `API_KEY` | `petnode_secret_key_2026` | Engine 上报 API Key 鉴权密钥 |
| `HMAC_KEY` | `petnode_hmac_secret_2026` | HMAC 签名密钥 |
| `MONGO_URI` | `mongodb://mongodb:27017` | MongoDB 连接串 |
| `MONGO_DB` | `petnode` | MongoDB 数据库名 |
| `MONGO_COLLECTION` | `received_records` | Engine 上报数据集合名 |
| `DATA_DIR` | `/app/data` | FileStorage 数据目录（仅 `file` 模式） |
| `JWT_SECRET` | `petnode_jwt_secret_2026` | **vx API** JWT 签名密钥（**生产环境务必修改**） |
| `WECHAT_APP_ID` | —（空） | 微信小程序 AppID（空时进入 mock 模式） |
| `WECHAT_APP_SECRET` | —（空） | 微信小程序 AppSecret（空时进入 mock 模式） |

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

## 13. 请求示例（cURL）

### Engine 上传数据

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

### vx API 示例

```bash
BASE="http://localhost:5000"

# 1. 微信身份校验（mock 模式，未配置 WECHAT_APP_ID 时有效）
curl -X POST "$BASE/api/v1/wechat/auth" \
  -H "Content-Type: application/json" \
  -d '{"code": "testcode123"}'

# 2. 绑定微信身份（使用 auth 返回的 wx_identity_token）
WX_TOKEN="<上一步返回的 wx_identity_token>"
curl -X POST "$BASE/api/v1/wechat/bind" \
  -H "Content-Type: application/json" \
  -d "{\"wx_identity_token\": \"$WX_TOKEN\"}"

# 3. 获取当前用户（使用 bind 返回的 access_token）
ACCESS_TOKEN="<bind 返回的 access_token>"
curl "$BASE/api/v1/me" \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 4. 获取宠物快照
PET_ID="109f156a015a"
curl "$BASE/api/v1/pets/$PET_ID/summary" \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 5. 呼吸频率序列（最近 50 条）
curl "$BASE/api/v1/pets/$PET_ID/respiration/series?limit=50" \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 6. 心率序列（指定时间段）
curl "$BASE/api/v1/pets/$PET_ID/heart-rate/series?start=2026-05-03T00:00:00&end=2026-05-03T12:00:00" \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 7. 事件列表（第一页）
curl "$BASE/api/v1/pets/$PET_ID/events?limit=10" \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 8. 事件列表（翻页，使用 next_cursor）
CURSOR="<上一步返回的 next_cursor>"
curl "$BASE/api/v1/pets/$PET_ID/events?cursor=$CURSOR&limit=10" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

---

## 14. vx 端集成指南

本节面向微信小程序（vx）开发者，描述各页面应调用哪些后端接口以及完整的调用流程。

### 13.1 端到端登录流程

```
vx 启动
  │
  ▼
wx.login() → 拿到 code
  │
  ▼
POST /api/v1/wechat/auth { code }
  │
  ├─ is_bound = true  → 直接拿到 access_token，存储到 wx.setStorageSync('token', token)
  │                     → 跳转首页
  │
  └─ is_bound = false → 存储 wx_identity_token（10 分钟有效）
                        → 展示注册/绑定引导页
                        → 用户确认后调用 POST /api/v1/wechat/bind
                        → 拿到 access_token，存储
                        → 跳转首页
```

### 13.2 vx 需要实现的函数/页面及对应接口

| 页面/函数 | 调用接口 | 触发时机 | 说明 |
|-----------|---------|---------|------|
| `app.js: onLaunch()` | `wx.login()` + `POST /wechat/auth` | 小程序启动 | 检查是否已绑定，已绑定则直接获取 access_token |
| 绑定页 `bind.js: onConfirm()` | `POST /wechat/bind` | 用户首次登录确认 | 传入 wx_identity_token，获取 access_token |
| 首页 `index.js: onShow()` | `GET /me` + `GET /pets/{id}/summary` | 每次页面展示 | 获取用户信息和宠物快照 |
| 首页 `index.js: startPolling()` | `GET /pets/{id}/summary` | 定时轮询（建议 10s 间隔） | 刷新宠物状态、呼吸、心率、事件 |
| 图表页 `chart.js: onLoad()` | `GET /pets/{id}/respiration/series` | 页面加载 | 传入 start/end 时间范围，获取呼吸曲线数据 |
| 图表页 `chart.js: onLoad()` | `GET /pets/{id}/heart-rate/series` | 页面加载 | 传入 start/end 时间范围，获取心率曲线数据 |
| 详情页 `detail.js: onLoad()` | `GET /pets/{id}/respiration/latest` | 详情页加载 | 显示最新呼吸频率 |
| 详情页 `detail.js: onLoad()` | `GET /pets/{id}/heart-rate/latest` | 详情页加载 | 显示最新心率 |
| 消息页 `events.js: onLoad()` | `GET /pets/{id}/events` | 页面加载及下拉加载更多 | 使用 cursor 分页 |

### 13.3 Token 管理建议

```javascript
// 存储 token
wx.setStorageSync('petnode_token', access_token);

// 读取 token（每次请求前）
const token = wx.getStorageSync('petnode_token');
if (!token) {
  // 重新走登录流程
  return redirectToLogin();
}

// 请求头携带 token
const header = { 'Authorization': `Bearer ${token}` };

// 处理 401 响应
if (res.data.code === 40101) {
  wx.removeStorageSync('petnode_token');
  redirectToLogin();
}
```

### 13.4 轮询建议

| 场景 | 建议间隔 | 调用接口 |
|------|---------|---------|
| 小程序前台、用户查看首页 | 10 秒 | `GET /pets/{id}/summary` |
| 小程序进入后台 | 暂停轮询 | — |
| 图表页实时刷新 | 30 秒 | `GET /pets/{id}/respiration/series`（最新 30 条） |
| 事件页新事件检查 | 60 秒 | `GET /pets/{id}/events?limit=5` |

> **注意：** 不要使用 1 秒以内的高频轮询，会触发服务端限流并耗尽设备电量。

### 13.5 pet_id 与 device_id 对应关系

vx 端通过 `GET /me` 获取 `pets` 列表，其中每项的 `device_id` 字段即为访问遥测接口时的路径参数 `pet_id`：

```javascript
// 获取用户信息和宠物列表
const res = await request('/api/v1/me');
const pets = res.data.pets;  // [{ device_id: "109f156a015a", pet_name: "旺财" }]

// 用 device_id 访问宠物接口
const petId = pets[0].device_id;  // "109f156a015a"
const summary = await request(`/api/v1/pets/${petId}/summary`);
```

---

> **文档版本：** v3.0 | **最后更新：** 2026-05-03 | **代码库：** `BassttElSevic/PetNode`