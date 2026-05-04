# MySQL 服务配置指南

## 概述

已为 PetNode C端模拟系统添加 MySQL 服务，用于把接收到的狗项圈数据拆分写入规范化表结构。

## 核心改动

### 1. **docker-compose.yml** - 添加 MySQL 服务
```yaml
mysql:
  image: mysql:8
  container_name: petnode-mysql
  ports:
    - "3306:3306"
  environment:
    - MYSQL_ROOT_PASSWORD=petnode_root_2026
    - MYSQL_DATABASE=petnode
    - MYSQL_USER=petnode_user
    - MYSQL_PASSWORD=petnode_password_2026
```

**关键参数**：
- 端口：**3306**（标准 MySQL 端口）
- 默认用户：`petnode_user`
- 默认密码：`petnode_password_2026`
- 数据库名：`petnode`
- root 密码：`petnode_root_2026`

### 2. **MySQLStorage** - 数据存储实现
新创建文件：`flask_server/storage/mysql_storage.py`

**核心特性**：
- ✅ 自动补齐 `user` / `device` / `trait_type` / `event_type` 基础字典
- ✅ 每次上报拆成多条 `telemetry_record`
- ✅ `event` / `event_phase` 自动进入 `event_instance`
- ✅ 支持按设备、时间、指标类型、事件实例查询

**表结构**：
```
user
device
trait_type
device_trait
event_type
event_instance
telemetry_record
```

**字段映射**：
- `device_id`：引擎上报的字符串 ID，会被稳定映射成 MySQL 的 BIGINT 主键，同时原始值保存在 `device.device_sn`
- `user_id`：默认写入 `1`，可通过环境变量覆盖
- `heart_rate` / `resp_rate` / `temperature` / `steps` / `battery` / `gps_lat` / `gps_lng` / `behavior`：拆成 `telemetry_record`
- `event` / `event_phase`：写入 `event_instance`

### 3. **app.py** - 添加 MySQL 后端支持
支持三种存储后端：
```python
# 环境变量 STORAGE_BACKEND 的值
- "file"   → FileStorage（本地文件存储）
- "mongo"  → MongoStorage（MongoDB，默认）
- "mysql"  → MySQLStorage（MySQL，按日期存储）
```

### 4. **requirements.txt** - 添加依赖
```
PyMySQL>=1.1,<2.0             # MySQL Python 客户端
```

## 使用方式

### 方式 1：使用 Docker Compose（推荐）

#### 启动 MySQL + Flask 服务
```bash
cd C_end_Simulator
docker compose up -d mysql flask-server
```

#### 切换为 MySQL 存储后端
编辑 `docker-compose.yml`，找到 `flask-server` 服务，修改：
```yaml
environment:
  - STORAGE_BACKEND=mysql  # 改为 mysql
```

然后重启服务：
```bash
docker compose restart flask-server
```

#### 启动完整系统（包括引擎）
```bash
docker compose up -d
```

### 方式 2：本地调试

#### 1. 启动 MySQL 服务
```bash
# 如果已安装 MySQL
mysql -u root -p

# 或使用 Docker
docker run -d \
  -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=petnode_root_2026 \
  -e MYSQL_DATABASE=petnode \
  -e MYSQL_USER=petnode_user \
  -e MYSQL_PASSWORD=petnode_password_2026 \
  mysql:8
```

#### 2. 安装 Python 依赖
```bash
cd flask_server
pip install -r requirements.txt
```

#### 3. 启动 Flask 服务
```bash
export STORAGE_BACKEND=mysql
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_DB=petnode
export MYSQL_USER=petnode_user
export MYSQL_PASSWORD=petnode_password_2026

python -m flask_server.app
```

## MySQL 配置环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `STORAGE_BACKEND` | `mongo` | 存储后端选择 |
| `MYSQL_HOST` | `localhost` | MySQL 服务器地址 |
| `MYSQL_PORT` | `3306` | MySQL 端口 |
| `MYSQL_DB` | `petnode` | 数据库名 |
| `MYSQL_USER` | `root` | 用户名 |
| `MYSQL_PASSWORD` | `` | 密码 |
| `MYSQL_CHARSET` | `utf8mb4` | 字符集 |

## 数据查询示例

### 查询所有数据
```sql
SELECT * FROM received_records;
```

### 按日期查询
```sql
SELECT * FROM received_records WHERE date = '2025-06-01';
```

### 按设备查询
```sql
SELECT * FROM received_records WHERE device_id = '109f156a015a' ORDER BY timestamp DESC;
```

### 按日期和设备查询
```sql
SELECT * FROM received_records 
WHERE date = '2025-06-01' AND device_id = '109f156a015a' 
ORDER BY timestamp DESC;
```

### 查询特定日期的数据条数
```sql
SELECT date, COUNT(*) as record_count FROM received_records GROUP BY date;
```

### 查询异常事件数据
```sql
SELECT * FROM received_records 
WHERE event IS NOT NULL 
ORDER BY date DESC, timestamp DESC;
```

## 每日数据存储工作流程

```
Engine 生成数据
    ↓
HttpExporter POST /api/data
    ↓
Flask app.py 接收 & 验证
    ↓
MySQLStorage.save()
    ↓
① 从 timestamp 提取日期 (YYYY-MM-DD)
② 添加 date 字段 (用于日期分类)
③ 添加 ingested_at (服务器接收时间)
④ INSERT INTO received_records
    ↓
每条记录都被标记上日期，便于后期按日期统计分析
```

## 监控和维护

### 检查 MySQL 连接状态
```bash
docker compose logs mysql
docker compose logs flask-server
```

### 进入 MySQL 容器
```bash
docker exec -it petnode-mysql mysql -u petnode_user -p petnode
```

### 备份数据
```bash
docker exec petnode-mysql mysqldump -u petnode_user -p petnode_password_2026 petnode > backup.sql
```

### 恢复数据
```bash
docker exec -i petnode-mysql mysql -u petnode_user -p petnode_password_2026 petnode < backup.sql
```

## 切换存储后端

**从 MongoDB 切换到 MySQL**：
1. 修改 `docker-compose.yml` 的 `STORAGE_BACKEND=mysql`
2. 重启 Flask 服务：`docker compose restart flask-server`
3. MySQL 表结构和基础字典会自动创建（如不存在）

**与 `crebas.sql` 的关系**：
- `crebas.sql` 是这套 MySQL 规范化模型的参考结构
- 当前代码已经按照这个模型自动建表和写入，不需要先手工导入 SQL
- 如果你想先人工建库，也可以先执行 `crebas.sql`，再启动服务

**从 MySQL 切换到 MongoDB**：
1. 修改 `docker-compose.yml` 的 `STORAGE_BACKEND=mongo`
2. 重启 Flask 服务：`docker compose restart flask-server`
3. 历史数据仍保存在 MongoDB 中

## 常见问题

### Q: "Can't connect to MySQL server"
**A**: 检查 MySQL 容器是否运行：
```bash
docker ps | grep mysql
docker compose logs mysql
```

### Q: "Access denied for user 'petnode_user'"
**A**: 检查密码是否正确，默认为 `petnode_password_2026`

### Q: 如何修改 MySQL 密码？
**A**: 编辑 `docker-compose.yml` 中的 `MYSQL_PASSWORD` 和 `mysql` 容器的 `MYSQL_ROOT_PASSWORD`，然后重新创建容器：
```bash
docker compose down
docker compose up -d mysql
```

### Q: 数据没有被存储到 MySQL
**A**: 
1. 检查 `STORAGE_BACKEND` 是否设为 `mysql`
2. 检查 Flask 启动日志：`docker compose logs flask-server`
3. 确保 MySQL 容器正常运行：`docker compose ps`

## 下一步

- ✅ MySQL 服务已部署
- ✅ 每日数据自动分类存储
- 📋 可选：创建定时备份脚本
- 📋 可选：添加数据分析接口
- 📋 可选：实现数据可视化面板

