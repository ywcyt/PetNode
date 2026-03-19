
# 1. 确保旧的数据被清空
echo "🧹 正在清理旧数据..."
rm -rf output_data/*

# 2. 直接使用底层 docker run 命令并发启动 3 个容器
echo "🚀 正在拉起 3 个并发容器..."
docker run -d --name demo_engine_1 -v $(pwd)/output_data:/app/output_data petnode-engine:latest --dogs 2 --interval 1 --ticks 99999
docker run -d --name demo_engine_2 -v $(pwd)/output_data:/app/output_data petnode-engine:latest --dogs 2 --interval 1 --ticks 99999
docker run -d --name demo_engine_3 -v $(pwd)/output_data:/app/output_data petnode-engine:latest --dogs 2 --interval 1 --ticks 99999

# 3. 打印正在运行的容器
echo -e "\n\033[0;32m=== 🚀 正在运行的 3 个 Docker 容器 ===\033[0m"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"

# 4. 倒计时 3 秒，等待数据产生
echo -e "\n\033[0;33m👉 准备查看实时数据流 (看 15 秒后自动退出并清理)...\033[0m"
sleep 3

# 5. 实时监控数据流
timeout 15 tail -f output_data/realtime_stream.jsonl

# 6. 打扫战场
echo -e "\n\033[0;31m=== 🧹 演示结束，开始清理环境 ===\033[0m"
docker rm -f demo_engine_1 demo_engine_2 demo_engine_3 > /dev/null
rm -rf output_data/*

echo -e "\033[0;32m✨ 清理完毕！环境已恢复如初！\033[0m\n"

