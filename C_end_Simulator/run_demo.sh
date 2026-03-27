# 1. 构建镜像
echo "🔨 正在构建 Docker 镜像..."
docker build -f flask_server/Dockerfile -t petnode-flask:latest .
docker build -f engine/Dockerfile -t petnode-engine:latest .

# 2. 确保旧的数据被清空
echo "🧹 正在清理旧数据..."
rm -rf output_data/*

# 3. 启动 Flask 容器（模拟云端服务器）
echo "☁️  正在部署 Flask 云端服务器 (监听 5000 端口)..."
docker run -d \
    --name demo_flask_cloud \
    -p 5000:5000 \
    -v $(pwd)/output_data/flask_data:/app/data \
    -e PYTHONUNBUFFERED=1 \
    -e DATA_DIR=/app/data \
    -e PORT=5000 \
    petnode-flask:latest

# 等待 Flask 服务器启动（健康检查）
echo "⏳ 等待 Flask 服务器启动..."
sleep 5

# 验证 Flask 服务器是否正常
if curl -s http://localhost:5000/api/health > /dev/null 2>&1; then
    echo "✅ Flask 云端服务器已就绪"
    curl -s http://localhost:5000/api/health | python -m json.tool
else
    echo "❌ Flask 服务器启动失败，退出"
    docker rm -f demo_flask_cloud > /dev/null
    exit 1
fi

# 4. 直接使用底层 docker run 命令并发启动 3 个 Engine 容器（客户端）
echo "🚀 正在拉起 3 个并发容器（通过公网域名 pppetnode.com 访问云端）..."

# 获取宿主机的实际 IP 地址（Docker 容器需要访问这个 IP）
HOST_IP=$(hostname -I | awk '{print $1}')
echo "📍 检测到宿主机 IP: ${HOST_IP}"

# Engine 容器 1：通过公网域名访问 Flask 容器
# 关键点：--api-url 使用 pppetnode.com:5000，强制走公网 DNS → 公网 IP → NAT → Docker 端口映射
docker run -d \
    --name demo_engine_1 \
    -v $(pwd)/output_data/engine1:/app/output_data \
    -e PYTHONUNBUFFERED=1 \
    --add-host="pppetnode.com:${HOST_IP}" \
    petnode-engine:latest \
    --dogs 2 \
    --interval 1 \
    --ticks 99999 \
    --api-url "http://pppetnode.com:5000/api/data" \
    --output-dir "/app/output_data" \
    --log-level INFO

# Engine 容器 2
docker run -d \
    --name demo_engine_2 \
    -v $(pwd)/output_data/engine2:/app/output_data \
    -e PYTHONUNBUFFERED=1 \
    --add-host="pppetnode.com:${HOST_IP}" \
    petnode-engine:latest \
    --dogs 2 \
    --interval 1 \
    --ticks 99999 \
    --api-url "http://pppetnode.com:5000/api/data" \
    --output-dir "/app/output_data" \
    --log-level INFO

# Engine 容器 3
docker run -d \
    --name demo_engine_3 \
    -v $(pwd)/output_data/engine3:/app/output_data \
    -e PYTHONUNBUFFERED=1 \
    --add-host="pppetnode.com:${HOST_IP}" \
    petnode-engine:latest \
    --dogs 2 \
    --interval 1 \
    --ticks 99999 \
    --api-url "http://pppetnode.com:5000/api/data" \
    --output-dir "/app/output_data" \
    --log-level INFO

# 5. 打印正在运行的容器
echo -e "\n\033[0;32m=== 🚀 正在运行的 Docker 容器 ===\033[0m"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"

# 6. 显示网络拓扑（强调公网通信）
echo -e "\n\033[0;36m=== 🌐 公网通信拓扑 ===\033[0m"
echo "┌─────────────────────────────────────────────────────────┐"
echo "│  ☁️ Flask 云端容器 (demo_flask_cloud)                    │"
echo "│     监听：0.0.0.0:5000                                  │"
echo "│     映射：宿主机 5000 → 容器 5000                        │"
echo "│     域名：pppetnode.com:5000                            │"
echo "└────────────────▲────────────────────────────────────────┘"
echo "                 │"
echo "                 │ 🌐 公网 HTTP (http://pppetnode.com:5000)"
echo "                 │ 路径：DNS 解析 → 公网 IP → NAT → Docker 映射"
echo "                 │"
echo "┌────────────────┼────────────────────────────────────────┐"
echo "│  ┌─────────────┴──────────┐  ┌────────────────────┐     │"
echo "│  │ Engine 容器 #1          │  │ Engine 容器 #2      │     │"
echo "│  │ (客户端 1, 2 只狗)       │  │ (客户端 2, 2 只狗)   │     │"
echo "│  └────────────────────────┘  └────────────────────┘     │"
echo "│  ┌────────────────────────────────────────────────┐     │"
echo "│  │ Engine 容器 #3                                  │     │"
echo "│  │ (客户端 3, 2 只狗)                               │     │"
echo "│  └────────────────────────────────────────────────┘     │"
echo "└─────────────────────────────────────────────────────────┘"
echo ""
echo "📊 总计：3 个客户端容器 × 2 只狗 = 6 条数据流并发上报"
echo "🔗 通信方式：Engine 容器 → DNS 解析 → 公网 → NAT → Flask 容器"
echo "✅ 完全模拟真实客户端通过网络访问云端服务器！"

# 7. 倒计时 3 秒，等待数据产生
echo -e "\n\033[0;33m👉 准备查看实时数据流 (看 20 秒后自动退出并清理)...\033[0m"
sleep 3

# 8. 实时监控数据流和日志（分屏显示）
echo -e "\n\033[0;36m=== 📊 Flask 云端接收日志 ===\033[0m"
timeout 20 docker logs --tail 5 -f demo_flask_cloud &
FLASK_LOG_PID=$!

echo -e "\n\033[0;36m=== 📈 Engine #1 实时数据流 ===\033[0m"
timeout 20 tail -f output_data/engine1/realtime_stream.jsonl &
ENGINE_LOG_PID=$!

# 等待监控结束
wait $FLASK_LOG_PID 2>/dev/null || true
wait $ENGINE_LOG_PID 2>/dev/null || true

# 9. 显示统计信息
echo -e "\n\033[0;36m=== 📊 数据统计 ===\033[0m"
echo "Flask 云端接收情况："
curl -s http://localhost:5000/api/health | python -m json.tool 2>/dev/null || echo "无法连接 Flask 服务器"

echo -e "\n各 Engine 容器数据生成情况："
for i in 1 2 3; do
    if [ -f "output_data/engine$i/engine_status.json" ]; then
        echo "Engine #$i:"
        cat "output_data/engine$i/engine_status.json" | python -m json.tool 2>/dev/null || echo "  无状态文件"
    fi
done

# 10. 打扫战场
echo -e "\n\033[0;31m=== 🧹 演示结束，开始清理环境 ===\033[0m"
echo "停止并删除容器..."
docker rm -f demo_engine_1 demo_engine_2 demo_engine_3 demo_flask_cloud > /dev/null 2>&1

echo "清理输出数据..."
rm -rf output_data/*

echo "清理悬空镜像..."
docker image prune -f > /dev/null 2>&1

echo -e "\033[0;32m✨ 清理完毕！环境已恢复如初！\033[0m\n"

