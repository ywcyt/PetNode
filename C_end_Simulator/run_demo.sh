#!/bin/bash

# 0. 清理上次运行可能残留的容器和网络
echo "🧹 清理可能残留的旧容器..."
docker rm -f demo_engine_1 demo_engine_2 demo_engine_3 demo_flask_cloud > /dev/null 2>&1
docker network rm petnode-net > /dev/null 2>&1

# 1. 创建共享 Docker 网络
docker network create petnode-net 2>/dev/null || true

# 2. 构建镜像
echo "🔨 正在构建 Docker 镜像..."
docker build --no-cache -f flask_server/Dockerfile -t petnode-flask:latest .
docker build -f engine/Dockerfile -t petnode-engine:latest .

# 2. 清理旧数据
echo "🧹 正在清理旧数据..."
rm -rf output_data/*

# 3. 启动 Flask 容器（云端）
echo "☁️  正在部署 Flask 云端服务器..."
docker run -d \
    --name demo_flask_cloud \
    --network petnode-net \
    -p 5000:5000 \
    -v $(pwd)/output_data/flask_data:/app/data \
    -e PYTHONUNBUFFERED=1 \
    -e DATA_DIR=/app/data \
    -e PORT=5000 \
    petnode-flask:latest

echo "⏳ 等待 Flask 服务器启动..."
sleep 5

if curl -s http://localhost:5000/api/health > /dev/null 2>&1; then
    echo "✅ Flask 云端服务器已就绪"
    curl -s http://localhost:5000/api/health | python3 -m json.tool
else
    echo "❌ Flask 服务器启动失败"
    docker rm -f demo_flask_cloud > /dev/null
    exit 1
fi

# 4. 启动 3 个 Engine 容器（走 Docker 内部网络）
echo "🚀 正在拉起 3 个并发 Engine 容器..."

for i in 1 2 3; do
    docker run -d \
        --name demo_engine_$i \
        --network petnode-net \
        -v $(pwd)/output_data/engine$i:/app/output_data \
        -e PYTHONUNBUFFERED=1 \
        petnode-engine:latest \
        --dogs 2 \
        --interval 1 \
        --ticks 99999 \
        --api-url "http://demo_flask_cloud:5000/api/data" \
        --output-dir "/app/output_data" \
        --log-level INFO
done

# 5-10 后面的监控、统计、清理代码保持不变...
echo -e "\n\033[0;32m=== 🚀 正在运行的 Docker 容器 ===\033[0m"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"

echo -e "\n\033[0;33m👉 准备查看实时数据流 (看 20 秒后自动退出并清理)...\033[0m"
sleep 3

echo -e "\n\033[0;36m=== 📊 Flask 云端接收日志 ===\033[0m"
timeout 20 docker logs --tail 5 -f demo_flask_cloud &
FLASK_LOG_PID=$!

echo -e "\n\033[0;36m=== 📈 Engine #1 实时数据流 ===\033[0m"
timeout 20 tail -f output_data/engine1/realtime_stream.jsonl 2>/dev/null &
ENGINE_LOG_PID=$!

wait $FLASK_LOG_PID 2>/dev/null || true
wait $ENGINE_LOG_PID 2>/dev/null || true

echo -e "\n\033[0;36m=== 📊 数据统计 ===\033[0m"
echo "Flask 云端接收情况："
curl -s http://localhost:5000/api/health | python3 -m json.tool 2>/dev/null || echo "无法连接 Flask 服务器"

echo -e "\n\033[0;31m=== 🧹 演示结束，开始清理环境 ===\033[0m"
docker rm -f demo_engine_1 demo_engine_2 demo_engine_3 demo_flask_cloud > /dev/null 2>&1
docker network rm petnode-net > /dev/null 2>&1
rm -rf output_data/*
docker image prune -f > /dev/null 2>&1
echo -e "\033[0;32m✨ 清理完毕！\033[0m\n"