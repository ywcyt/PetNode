# PetNode 内部函数文档

> **适用范围：** `flask_server/services/` 包中的内部函数  
> **调用方式：** Flask 路由层（blueprints）→ 服务层（services）→ MongoDB  
> **最后更新：** 2026-05-03

---

## 目录

1. [概述与架构说明](#1-概述与架构说明)
2. [调用约定与错误处理](#2-调用约定与错误处理)
3. [identity — 用户身份哈希工具](#3-identity--用户身份哈希工具)
4. [binding — 绑定与解绑服务](#4-binding--绑定与解绑服务)
5. [telemetry — 遥测数据查询服务](#5-telemetry--遥测数据查询服务)
6. [HTTP 路由与内部函数的对应关系](#6-http-路由与内部函数的对应关系)
7. [vx 端如何依赖这些内部函数](#7-vx-端如何依赖这些内部函数)
8. [错误码速查](#8-错误码速查)

---

## 1. 概述与架构说明

PetNode 后端采用三层架构：

```
vx 微信小程序
      │  HTTP JSON
      ▼
Flask 路由层（blueprints/）
      │  Python 函数调用
      ▼
服务层（services/）   ←── 本文档描述的内部函数所在层
      │  MongoDB 查询
      ▼
数据库（MongoDB，通过 db.get_db() 获取句柄）
```

**服务层不对外暴露 HTTP 接口**，仅供路由层调用。Flask 与 MongoDB 部署在同一容器内，不需要额外的 HTTP 层。

### 服务层模块结构

```
flask_server/services/
├── __init__.py        重新导出所有公开函数
├── identity.py        用户身份规范化与哈希工具
├── binding.py         微信/设备绑定与解绑业务逻辑
└── telemetry.py       宠物遥测数据查询（呼吸、心率、事件）
```

---

## 2. 调用约定与错误处理

### 数据库句柄

所有服务函数均以 **MongoDB 数据库句柄**（`db`）为第一个参数：

```python
from flask_server.db import get_db
db = get_db()
result = some_service_function(db, user_id, ...)
```

### 异常规范

服务层通过抛出标准 Python 异常来表达错误，路由层负责将异常转换为 HTTP 响应：

| 异常类型 | 含义 | 路由层 HTTP 状态码 |
|----------|------|---------------------|
| `ValueError` | 参数缺失或格式无效 | 422 |
| `PermissionError` | 用户无权访问 | 403 |
| `LookupError` | 数据不存在 | 404 |
| `RuntimeError` | 并发冲突或系统错误 | 409 |

---

## 3. identity — 用户身份哈希工具

**模块路径：** `flask_server/services/identity.py`

用于生成稳定的用户匿名哈希标识（`user_hash`），供对外展示或数据打标使用，不替代内部 `user_id`。

---

### `normalize_identity(raw_name: str) -> str`

**作用：** 规范化用户标识字符串（去首尾空格 + 转小写），保证同一来源不同大小写写法能映射到相同哈希输入。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `raw_name` | str | ✅ | 原始标识（用户名、邮箱等） |

| 返回值 | 类型 | 说明 |
|--------|------|------|
| 规范化字符串 | str | strip + lower 结果 |

**异常：**
- `ValueError` — `raw_name` 为空或全为空白

**示例：**
```python
normalize_identity("  Alice  ")  # → "alice"
normalize_identity("BOB@EXAMPLE.COM")  # → "bob@example.com"
```

---

### `build_user_hash(user_id: str, secret: str | None = None) -> str`

**作用：** 使用 HMAC-SHA256 算法生成 24 字符十六进制匿名哈希。  
密钥从环境变量 `HASH_SECRET` 读取（生产环境务必设置）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | str | ✅ | 系统用户 ID（UUID 字符串） |
| `secret` | str \| None | 否 | HMAC 密钥；为 None 时读取 `HASH_SECRET` 环境变量 |

| 返回值 | 类型 | 说明 |
|--------|------|------|
| `user_hash` | str | 24 字符十六进制字符串，如 `"a3f2c1d4e5b6a7f8c9d0e1f2"` |

**异常：**
- `ValueError` — `user_id` 为空
- `RuntimeError` — `secret` 为空（防止无密钥哈希）

**安全说明：**
- 使用 HMAC，不可从哈希反推 `user_id`
- 相同 `user_id` + `secret` 始终生成相同哈希（稳定性）
- 不同 `user_id` 生成不同哈希（唯一性）

---

### `get_or_create_user_hash(db, user_id: str) -> str`

**作用：** 优先从 `users` 集合读取已存在的 `user_hash`；不存在则生成并写入（幂等操作）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `db` | Database | ✅ | MongoDB 数据库句柄 |
| `user_id` | str | ✅ | 系统用户 ID |

| 返回值 | 类型 | 说明 |
|--------|------|------|
| `user_hash` | str | 该用户的稳定哈希标识 |

**异常：**
- `ValueError` — `user_id` 为空

**数据库副作用：** 若 `users[user_id].user_hash` 不存在，写入该字段。

---

## 4. binding — 绑定与解绑服务

**模块路径：** `flask_server/services/binding.py`

处理用户与微信身份、用户与宠物设备之间的绑定关系。

---

### `bind_user_to_wechat(db, user_id, openid, unionid=None) -> dict`

**作用：** 将系统用户与微信身份绑定（幂等）。若该微信身份已绑定**同一**用户则直接返回已绑定状态；若已绑定**其他**用户则抛出 `PermissionError`。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `db` | Database | ✅ | MongoDB 数据库句柄 |
| `user_id` | str | ✅ | 系统用户 ID |
| `openid` | str | ✅ | 微信 openid |
| `unionid` | str \| None | 否 | 微信 unionid（开放平台场景） |

**返回值：**
```json
{
  "bind_status": "bound",
  "user_id": "550e8400-...",
  "bound_at": "2026-05-03T12:00:00+00:00"
}
```
或
```json
{
  "bind_status": "already_bound",
  "user_id": "550e8400-...",
  "bound_at": "2026-05-01T09:00:00+00:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `bind_status` | str | `"bound"` 新绑定 / `"already_bound"` 已绑定 |
| `user_id` | str | 系统用户 ID |
| `bound_at` | str | 绑定时间（ISO 8601） |

**异常：**
- `ValueError` — `user_id` 或 `openid` 为空
- `PermissionError` — 该微信身份已绑定其他用户
- `RuntimeError` — 并发写入导致唯一索引冲突

**数据库副作用：** 向 `wechat_bindings` 集合写入绑定记录。

---

### `unbind_user_from_wechat(db, user_id: str) -> dict`

**作用：** 解除用户的微信绑定。若未绑定则幂等返回 `not_bound`。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `db` | Database | ✅ | MongoDB 数据库句柄 |
| `user_id` | str | ✅ | 系统用户 ID |

**返回值：**
```json
{
  "unbind_status": "unbound",
  "user_id": "550e8400-...",
  "unbound_at": "2026-05-03T12:00:00+00:00"
}
```
或
```json
{
  "unbind_status": "not_bound",
  "user_id": "ghost_user",
  "unbound_at": null
}
```

**异常：**
- `ValueError` — `user_id` 为空

**数据库副作用：** 从 `wechat_bindings` 集合删除记录。

---

### `bind_user_to_device(db, user_id, device_id, pet_name="") -> dict`

**作用：** 将用户与宠物设备绑定（幂等）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `db` | Database | ✅ | MongoDB 数据库句柄 |
| `user_id` | str | ✅ | 系统用户 ID |
| `device_id` | str | ✅ | 设备唯一标识（等同于 `pet_id`） |
| `pet_name` | str | 否 | 宠物昵称，默认空字符串 |

**返回值：**
```json
{
  "bind_status": "bound",
  "user_id": "550e8400-...",
  "device_id": "109f156a015a",
  "added_at": "2026-05-03T12:00:00+00:00"
}
```

**异常：**
- `ValueError` — `user_id` 或 `device_id` 为空

**数据库副作用：** 向 `user_pets` 集合写入关联记录。

---

### `unbind_user_from_device(db, user_id, device_id) -> dict`

**作用：** 解除用户与宠物设备的绑定。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `db` | Database | ✅ | MongoDB 数据库句柄 |
| `user_id` | str | ✅ | 系统用户 ID |
| `device_id` | str | ✅ | 设备唯一标识 |

**返回值：**
```json
{
  "unbind_status": "unbound",
  "user_id": "550e8400-...",
  "device_id": "109f156a015a",
  "unbound_at": "2026-05-03T12:00:00+00:00"
}
```

**异常：**
- `ValueError` — `user_id` 或 `device_id` 为空

**数据库副作用：** 从 `user_pets` 集合删除记录。

---

### `assert_user_owns_pet(db, user_id, pet_id) -> None`

**作用：** 权限断言——验证用户是否有权访问该宠物设备。由所有遥测查询函数内部调用。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `db` | Database | ✅ | MongoDB 数据库句柄 |
| `user_id` | str | ✅ | 系统用户 ID（来自 JWT sub 字段） |
| `pet_id` | str | ✅ | 宠物设备 ID（路径参数） |

**返回值：** `None`（通过即无返回值）

**异常：**
- `PermissionError` — `user_pets` 集合中不存在 `{user_id, device_id}` 记录

---

## 5. telemetry — 遥测数据查询服务

**模块路径：** `flask_server/services/telemetry.py`

所有函数均先调用 `assert_user_owns_pet()` 进行权限校验，再执行 MongoDB 查询。

---

### `get_pet_summary(db, user_id, pet_id) -> dict`

**作用：** 获取宠物最新状态快照，汇总呼吸、心率、行为状态和当前事件。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `db` | Database | ✅ | MongoDB 数据库句柄 |
| `user_id` | str | ✅ | 系统用户 ID（用于权限校验） |
| `pet_id` | str | ✅ | 宠物设备 ID |

**返回值：**
```json
{
  "pet_id": "109f156a015a",
  "dog_status": "resting",
  "latest_respiration_bpm": 22.5,
  "latest_heart_rate_bpm": 82.0,
  "current_event": "fever",
  "current_event_phase": "onset",
  "last_reported_at": "2026-05-03T10:00:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `pet_id` | str | 宠物设备 ID |
| `dog_status` | str \| null | 行为状态（sleeping/resting/walking/running） |
| `latest_respiration_bpm` | float \| null | 最新呼吸频率 |
| `latest_heart_rate_bpm` | float \| null | 最新心率 |
| `current_event` | str \| null | 当前事件名称（无则为 null） |
| `current_event_phase` | str \| null | 事件阶段（onset/peak/recovery） |
| `last_reported_at` | str \| null | 最新数据时间戳 |

**异常：**
- `PermissionError` — 用户无权访问
- `LookupError` — 宠物不存在或暂无数据

---

### `get_latest_respiration(db, user_id, pet_id) -> dict`

**作用：** 获取最新一条呼吸频率采样值。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `db` | Database | ✅ | MongoDB 数据库句柄 |
| `user_id` | str | ✅ | 系统用户 ID |
| `pet_id` | str | ✅ | 宠物设备 ID |

**返回值：**
```json
{
  "pet_id": "109f156a015a",
  "unit": "bpm",
  "value_bpm": 22.5,
  "ts": "2026-05-03T10:00:00"
}
```

**异常：**
- `PermissionError` — 用户无权访问
- `LookupError` — 暂无呼吸频率数据

---

### `get_respiration_series(db, user_id, pet_id, start=None, end=None, limit=50) -> dict`

**作用：** 获取呼吸频率时间序列，支持时间范围和条数限制。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `db` | Database | ✅ | MongoDB 数据库句柄 |
| `user_id` | str | ✅ | 系统用户 ID |
| `pet_id` | str | ✅ | 宠物设备 ID |
| `start` | str \| None | 否 | 起始时间（ISO 8601） |
| `end` | str \| None | 否 | 结束时间（ISO 8601） |
| `limit` | int | 否 | 最多返回条数（默认 50，最大 500） |

**返回值：**
```json
{
  "pet_id": "109f156a015a",
  "unit": "bpm",
  "count": 3,
  "points": [
    { "ts": "2026-05-01T10:00:00", "value_bpm": 20.0 },
    { "ts": "2026-05-02T10:00:00", "value_bpm": 21.0 },
    { "ts": "2026-05-03T10:00:00", "value_bpm": 22.0 }
  ]
}
```

**异常：**
- `PermissionError` — 用户无权访问
- `ValueError` — `limit` 无法解析为整数

---

### `get_latest_heart_rate(db, user_id, pet_id) -> dict`

**作用：** 获取最新一条心率采样值。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `db` | Database | ✅ | MongoDB 数据库句柄 |
| `user_id` | str | ✅ | 系统用户 ID |
| `pet_id` | str | ✅ | 宠物设备 ID |

**返回值：**
```json
{
  "pet_id": "109f156a015a",
  "unit": "bpm",
  "value_bpm": 82.0,
  "ts": "2026-05-03T10:00:00"
}
```

**异常：**
- `PermissionError` — 用户无权访问
- `LookupError` — 暂无心率数据

---

### `get_heart_rate_series(db, user_id, pet_id, start=None, end=None, limit=50) -> dict`

**作用：** 获取心率时间序列，支持时间范围和条数限制。

参数与 `get_respiration_series()` 完全相同，返回值结构相同，区别仅在于 `value_bpm` 为心率值。

---

### `list_pet_events(db, user_id, pet_id, cursor=None, limit=20, event_type=None, start=None, end=None) -> dict`

**作用：** 获取宠物事件列表，支持 cursor 分页、时间范围过滤、事件类型过滤。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `db` | Database | ✅ | MongoDB 数据库句柄 |
| `user_id` | str | ✅ | 系统用户 ID |
| `pet_id` | str | ✅ | 宠物设备 ID |
| `cursor` | str \| None | 否 | 分页游标（上次响应的 `next_cursor`），优先级高于 `start/end` |
| `limit` | int | 否 | 每页条数（默认 20，最大 100） |
| `event_type` | str \| None | 否 | 事件类型过滤（如 `"fever"`、`"injury"`） |
| `start` | str \| None | 否 | 起始时间过滤（ISO 8601），cursor 存在时忽略 |
| `end` | str \| None | 否 | 结束时间过滤（ISO 8601），cursor 存在时忽略 |

**返回值：**
```json
{
  "pet_id": "109f156a015a",
  "items": [
    {
      "ts": "2026-05-03T10:00:00",
      "type": "fever",
      "phase": "onset",
      "behavior": "resting"
    }
  ],
  "next_cursor": "2026-05-02T10:00:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `pet_id` | str | 宠物设备 ID |
| `items` | list | 事件项列表（按时间降序） |
| `items[].ts` | str | 事件时间戳 |
| `items[].type` | str | 事件类型（fever/injury 等） |
| `items[].phase` | str \| null | 事件阶段（onset/peak/recovery） |
| `items[].behavior` | str \| null | 当时行为状态 |
| `next_cursor` | str \| null | 下一页游标；无更多数据时为 null |

**分页说明：**
- 第一次请求：不传 `cursor`，按时间降序返回最新 N 条
- 翻下一页：将 `next_cursor` 作为 `cursor` 参数传入
- `next_cursor` 为 null 表示无更多数据

**异常：**
- `PermissionError` — 用户无权访问
- `ValueError` — `limit` 无法解析为整数

---

## 6. HTTP 路由与内部函数的对应关系

| HTTP 路由 | Blueprint | 调用的服务函数 |
|-----------|-----------|----------------|
| `POST /api/v1/wechat/auth` | `wechat_bp` | （内联 MongoDB 查询） |
| `POST /api/v1/wechat/bind` | `wechat_bp` | `bind_user_to_wechat()` |
| `POST /api/v1/wechat/unbind` | `wechat_bp` | `unbind_user_from_wechat()` |
| `GET /api/v1/me` | `users_bp` | （内联 MongoDB 查询） |
| `GET /api/v1/pets/{pet_id}/summary` | `pets_bp` | `get_pet_summary()` |
| `GET /api/v1/pets/{pet_id}/respiration/latest` | `pets_bp` | `get_latest_respiration()` |
| `GET /api/v1/pets/{pet_id}/respiration/series` | `pets_bp` | `get_respiration_series()` |
| `GET /api/v1/pets/{pet_id}/heart-rate/latest` | `pets_bp` | `get_latest_heart_rate()` |
| `GET /api/v1/pets/{pet_id}/heart-rate/series` | `pets_bp` | `get_heart_rate_series()` |
| `GET /api/v1/pets/{pet_id}/events` | `pets_bp` | `list_pet_events()` |

---

## 7. vx 端如何依赖这些内部函数

vx（微信小程序）端**不直接调用内部函数**，而是通过 HTTP API 间接触发这些函数。以下是 vx 端的完整调用流程：

### 7.1 登录与绑定流程

```
vx 端                               Flask 服务层
──────────────────────────────────────────────────
wx.login()                          
  → 获得临时 code
POST /wechat/auth { code }          
  ← { is_bound, wx_identity_token }
  
  若 is_bound = false:
  POST /wechat/bind { wx_identity_token }
    服务层调用: bind_user_to_wechat()
    ← { bind_status, user_id, access_token }
    
  若 is_bound = true:
    直接使用响应中的 access_token
    
保存 access_token 到本地存储
```

### 7.2 首页数据加载

```
vx 首页                             Flask 服务层
──────────────────────────────────────────────────
GET /pets/{pet_id}/summary          
  Authorization: Bearer <token>
  服务层调用: get_pet_summary()
    → assert_user_owns_pet()（权限校验）
    → 查 received_records 最新记录
  ← { dog_status, latest_respiration_bpm, 
      latest_heart_rate_bpm, current_event }
```

### 7.3 图表页数据加载

```
vx 图表页                           Flask 服务层
──────────────────────────────────────────────────
GET /pets/{pet_id}/respiration/series?start=...&end=...
  服务层调用: get_respiration_series()
  ← { count, points: [{ts, value_bpm}] }

GET /pets/{pet_id}/heart-rate/series?start=...&end=...
  服务层调用: get_heart_rate_series()
  ← { count, points: [{ts, value_bpm}] }
```

### 7.4 事件列表分页

```
vx 事件页                           Flask 服务层
──────────────────────────────────────────────────
GET /pets/{pet_id}/events?limit=20  （第一页）
  服务层调用: list_pet_events()
  ← { items: [...], next_cursor: "2026-05-01T..." }

GET /pets/{pet_id}/events?cursor=2026-05-01T...&limit=20  （翻页）
  ← { items: [...], next_cursor: null }  （无更多）
```

### 7.5 vx 端需要实现的关键逻辑

| 功能 | vx 端需要做什么 |
|------|----------------|
| 登录 | 调用 `wx.login()` 取 code，POST `/wechat/auth`，若未绑定再 POST `/wechat/bind` |
| Token 管理 | 将 `access_token` 存入 `wx.setStorageSync()`，每次请求携带 `Authorization` |
| Token 续期 | 收到 `401` + `code=40101` 时重新走登录流程 |
| 首页 | GET `/pets/{pet_id}/summary`，渲染状态卡片 |
| 呼吸图表 | GET `/pets/{pet_id}/respiration/series?start=...&end=...` |
| 心率图表 | GET `/pets/{pet_id}/heart-rate/series?start=...&end=...` |
| 事件列表 | GET `/pets/{pet_id}/events?limit=20`，上拉加载时带 `cursor` |
| 解绑 | POST `/wechat/unbind`（需登录态） |

---

## 8. 错误码速查

| code | HTTP | 触发场景 | 影响的服务函数 |
|------|------|----------|----------------|
| `40101` | 401 | access_token 无效或已过期 | — |
| `40102` | 400 | 微信 code 无效 | — |
| `40103` | 401 | wx_identity_token 无效或已过期 | — |
| `40301` | 403 | 用户无权访问该宠物 | `assert_user_owns_pet()` → 所有遥测查询 |
| `40401` | 404 | 宠物不存在或暂无数据 | `get_pet_summary()`、`get_latest_*()` |
| `40901` | 409 | 微信已绑定其他账号 / 并发冲突 | `bind_user_to_wechat()` |
| `42201` | 422 | 参数缺失或格式无效 | 所有接收 `limit` 的遥测函数 |
| `50001` | 502 | 微信服务器请求超时 | — |
