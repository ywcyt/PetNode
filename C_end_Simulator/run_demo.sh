#!/bin/bash
# run_demo.sh —— PetNode 第二阶段完整系统演示（基于 docker-compose.yml）
#
# 启动完整的第二阶段系统：
#   rabbitmq + mongodb + flask-server + mq-worker + engine
#
# 演示 20 秒后自动清理所有容器和卷数据。
#
# 用法：
#   cd C_end_Simulator/
#   bash run_demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ────────────────── 颜色常量 ──────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ────────────────── 步骤 0：清理上次残留 ──────────────────
echo -e "${CYAN}${BOLD}============================================================${RESET}"
echo -e "${CYAN}${BOLD}  🐾 PetNode 第二阶段演示启动脚本${RESET}"
echo -e "${CYAN}${BOLD}============================================================${RESET}"
echo
echo -e "${YELLOW}🧹 清理可能残留的旧容器和数据卷...${RESET}"
docker compose down --volumes --remove-orphans > /dev/null 2>&1 || true
rm -rf output_data/*

# ────────────────── 步骤 1：构建镜像 ──────────────────
echo -e "${YELLOW}🔨 构建 Docker 镜像（首次运行会较慢）...${RESET}"
docker compose build

# ────────────────── 步骤 2：启动完整系统 ──────────────────
echo -e "\n${YELLOW}🚀 启动完整第二阶段系统（rabbitmq + mongodb + flask-server + mq-worker + engine）...${RESET}"
docker compose up -d

# ────────────────── 步骤 3：等待 Flask 健康检查通过 ──────────────────
echo -e "\n${YELLOW}⏳ 等待 Flask 服务器健康检查通过（最多 60 秒）...${RESET}"
MAX_WAIT=60
WAITED=0
until curl -s http://localhost:5000/api/health > /dev/null 2>&1; do
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        echo -e "${RED}❌ Flask 服务器在 ${MAX_WAIT} 秒内未就绪，终止演示${RESET}"
        docker compose logs flask-server | tail -20
        docker compose down --volumes > /dev/null 2>&1 || true
        exit 1
    fi
    sleep 2
    WAITED=$((WAITED + 2))
    echo -e "   已等待 ${WAITED}s..."
done
echo -e "${GREEN}✅ Flask 服务器已就绪${RESET}"
curl -s http://localhost:5000/api/health | python3 -m json.tool 2>/dev/null || true

# ────────────────── 步骤 4：显示正在运行的容器 ──────────────────
echo -e "\n${GREEN}${BOLD}=== 🚀 正在运行的 Docker 容器 ===${RESET}"
docker compose ps

# ────────────────── 步骤 5：实时查看日志（20 秒）──────────────────
echo -e "\n${YELLOW}👉 准备查看实时数据流（查看 20 秒后自动清理）...${RESET}"
sleep 3

echo -e "\n${CYAN}=== 📊 Flask 服务器接收日志 ===${RESET}"
timeout 20 docker compose logs --tail 5 -f flask-server 2>/dev/null &
FLASK_LOG_PID=$!

echo -e "\n${CYAN}=== 📨 MQ Worker 消费日志 ===${RESET}"
timeout 20 docker compose logs --tail 5 -f mq-worker 2>/dev/null &
MQ_LOG_PID=$!

wait $FLASK_LOG_PID 2>/dev/null || true
wait $MQ_LOG_PID   2>/dev/null || true

# ────────────────── 步骤 6：最终统计 ──────────────────
echo -e "\n${CYAN}${BOLD}=== 📊 最终数据统计 ===${RESET}"
echo -e "Flask 健康检查结果："
curl -s http://localhost:5000/api/health | python3 -m json.tool 2>/dev/null \
    || echo "无法连接 Flask 服务器"

# ────────────────── 步骤 7：自动清理 ──────────────────
echo -e "\n${RED}${BOLD}=== 🧹 演示结束，开始清理环境 ===${RESET}"
docker compose down --volumes --remove-orphans > /dev/null 2>&1 || true
rm -rf output_data/*
echo -e "${GREEN}✨ 清理完毕！所有容器、网络及数据卷已移除。${RESET}\n"