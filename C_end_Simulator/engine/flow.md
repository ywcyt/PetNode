# docker 改造流程

## 1. 改造目标

本次改造的核心目标有四个：

1. **移除 engine 生成的 `user_id` 指标**
   - 让 engine 只负责生成设备/宠物侧数据，不再负责用户身份信息。
2. **让 Docker 负责执行数据生成任务**
   - 将数据生成和传输任务稳定地运行在容器环境中。
3. **将 TUI 改造成“数据传输监视终端”**
   - 不再作为登录/业务操作终端，而是用于在终端中监视数据发送情况、链路状态和任务运行状态。
4. **将绑定关系迁移到 Flask + MySQL**
   - 后续通过 Flask API 处理用户与设备的绑定，并落到 MySQL 中管理。

---

## 2. 当前项目现状

根据当前 `PetNode` 项目设计，系统职责大致如下：

- `engine/`：生成模拟狗项圈数据
- `flask_server/`：接收上报数据并进行存储
- `ui_tui/`：当前偏向“登录  + 控制引擎”
- `output_data/`：共享数据目录，用于 engine 和 TUI/GUI 之间交换数据

目前存在的问题：

1. `user_id` 出现在 engine 的数据模型和输出 record 中，导致用户绑定逻辑和数据生成逻辑耦合。
2. TUI 当前仍然偏向业务登录界面，而不是链路监控终端。
3. 用户-设备绑定关系还没有完全迁移到 Flask + MySQL 侧。

---

## 3. 改造后的职责划分

### 3.1 engine

负责：
- 生成模拟数据
- 输出数据到文件 / HTTP / MQ
- 提供运行状态和传输状态

不再负责：
- 生成 `user_id`
- 管理用户绑定关系

### 3.2 Flask + MySQL

负责：
- 提供绑定 API
- 管理用户、设备和绑定关系
- 后续支持按��定关系查询设备数据

### 3.3 TUI

负责：
- 监视数据传输状态
- 监视 engine 运行状态
- 展示最近传输结果
- 进行基本控制（暂停/恢复/停止/刷新）

不再负责：
- 用户登录态生成
- 本地 `user_id` 生成
- 基于用户身份直接筛选数据

---

## 4. 总体改造步骤

整个流程建议分成 **4 个阶段，7 个具体步骤**。

---

# 第一阶段：数据模型瘦身

## Step 1：重定义职责边界

目标：
- 明确 engine 只负责“生成和发送数据”
- 明确 Flask + MySQL 负责“绑定关系”
- 明确 TUI 负责“传输监视”

输出：
- 新的模块职责说明
- 新的数据流方案

---

## Step 2：移除 engine 中的 `user_id`

需要调整的内容包括：

### 2.1 engine 数据模型
- 从 `DogProfile` 中移除 `user_id`
- `random_profile()` 不再生成 `user_id`

### 2.2 record 输出结构
- 从 `generate_one_record()` 的输出中删除 `user_id`
- 保留 `device_id` 作为设备唯一标识

### 2.3 engine 调度入口
- 弱化或移除 `--users` 的业务意义
- 将 engine 进一步收敛为“设备数据生成器”

### 2.4 exporter / Flask 接收兼容
- Flask 接收逻辑不再要求 record 中存在 `user_id`
- Mongo / File / MQ 等接收链路兼容新的 record 结构

### 2.5 tests 更新
- 删除测试里对 `user_id` 的断言
- 更新数据结构相关测试

验收标准：
- engine 可正常运行
- 输出数据中不再包含 `user_id`
- 现有链路不会因为缺少 `user_id` 而报错

---

# 第二阶段：Docker 固化生成任务

## Step 3：让 Docker 固定执行 engine 生成任务

目标：
- 不再依赖手动临时执行命令
- 使用 Docker / docker-compose 统一管理生成任务

需要完成：

### 3.1 明确运行模式
建议优先支持：
- **常驻模式**：持续生成、持续发送，适合监控
- 后续可选支持：批量任务模式

### 3.2 固定容器启动参数
包括：
- 输出目录
- tick 间隔
- exporter 类型
- 日志级别
- 上报目标地址

### 3.3 明确状态输出
为了给 TUI 监视使用，engine 需要输出：
- 运行状态
- 当前 tick
- 最近发送时间
- 最近���送结果
- 错误次数/重试次数

验收标准：
- `docker compose up` 后 engine 能自动启动
- 数据能够稳定生成并进入既定输出链路
- 状态信息可被外部读取

---

# 第三阶段：TUI 重构为传输监视终端

## Step 4：清理旧 TUI 用户逻辑

需要调整：
- 弱化或删除 `UserStore`
- 弱化或删除 `LoginScreen`
- 去掉本地生成 `user_id` 的逻辑
- 去掉按 `user_id` 过滤 record 的逻辑

保留：
- 应用入口
- Dashboard 主界面
- 基本控制指令能力

验收标准：
- TUI 可以脱离“登录型业务逻辑”独立运行
- 不依赖 `user_id`

---

## Step 5：补充传输监控状态输出

为了让 TUI 真正监视链路，需要提供监控数据来源。

建议优先采用共享文件方式，在 `output_data/` 或专用目录中补充类似文件：

- `transport_status.json`
- `transport_metrics.json`
- `transport_errors.jsonl`
- `recent_transfers.jsonl`

这些文件可以包含：
- 当前 exporter 类型
- 最近一次发送是否成功
- 最近失败原因
- 成功数 / 失败数 / 重试数
- 最近 N 条传输结果

验收标准：
- TUI 可以读取到专门的传输状态数据
- 监控信息不再只依赖原始狗数据 record

---

## Step 6：重做 TUI Dashboard

新的 TUI Dashboard 建议分为 5 个区域：

### 6.1 系统总状态
- engine 状态：running / paused / stopped
- 当前 tick
- exporter 类型
- 最近发送时间

### 6.2 传输统计
- 成功发送数
- 失败发送数
- 重试次数
- 成功率
- 发送速率

### 6.3 链路健康
- Flask 健康状态
- HTTP 最近状态码 / 延迟
- RabbitMQ 状态（若启用）
- 文件写入状态（若为 file exporter）

### 6.4 最近传输记录
展示最近 N 条：
- `device_id`
- `timestamp`
- 通道类型
- 结果
- 错误摘要

### 6.5 控制面板
支持：
- 暂停
- 恢复
- 停止
- 刷新
- 调整 tick 间隔

验收标准：
- TUI 能作为“监视终端”使用
- 可以直接观察当前数据传输情况

---

# 第四阶段：Flask + MySQL 承接绑定关系

## Step 7：实现绑定能力

目标：
- 将用户-设备绑定关系从 engine/TUI 中剥离，迁移到 Flask + MySQL

需要完成：

### 7.1 完善 MySQL 存储层
在 `flask_server/storage/mysql_storage.py` 中补全：
- MySQL 连接
- 建表逻辑
- 绑定关系存储
- 查询绑定关系

### 7.2 设计基础表结构
建议至少包含：

#### users
- id
- username
- created_at

#### devices
- id
- device_id
- device_name（可选）
- created_at

#### user_device_bindings
- id
- user_id
- device_id
- bound_at
- status

### 7.3 提供 Flask API
建议至少提供：
- 绑定设备接口
- 解绑设备接口
- 查询用户绑定设备接口
- 查询设备绑定关系接口

### 7.4 后续数据查询方式
未来如果要按用户查数据：
1. 先通过 MySQL 查出该用户绑定的 `device_id`
2. 再按 `device_id` 查询记录

验收标准：
- 用户绑定关系完全由 Flask + MySQL 管理
- engine 不再感知用户绑定逻辑

---

## 5. 推荐实施顺序

为了降低改造风险，建议按下面顺序推进：

### 第一优先级
1. 移除 `user_id`
2. 确保 engine 正常运行
3. 确保 Docker 可以稳定跑生成任务

### 第二优先级
4. 输出传输监控状态
5. 重构 TUI 为监视终端

### 第三优先级
6. 实现 Flask + MySQL 绑定 API
7. 后续再接业务查询逻辑

---

## 6. 风险点

### 风险 1：旧代码对 `user_id` 耦合较深
处理方式：
- 优先全局排查 `user_id` 的使用点
- 分模块逐步删除

### 风险 2：TUI 当前设计目标与新目标不一致
处理方式：
- 不做小修小补，直接重定义为“监控终端”

### 风险 3：绑定逻辑与传输链路混改导致联调困难
处理方式：
- 先打通“生成 -> 发送 -> 监控”主链路
- 再做“绑定 -> 查询”业务链路

---

## 7. 最终改造结果

改造完成后，系统应形成如下结构：

- **engine**：只生成和发送设备数据
- **Docker**：稳定执行数据生成/传输任务
- **TUI**：专注监视链路状态和传输情况
- **Flask + MySQL**：专注处理绑定关系和后续业务查询

这样可以实现：

1. 数据生成职责清晰
2. 用户绑定职责清晰
3. TUI 的定位更明确
4. 后续扩展接口和数据库时不会反复影响 engine