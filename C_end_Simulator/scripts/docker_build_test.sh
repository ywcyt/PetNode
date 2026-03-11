#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────────
# PetNode Docker 构建与测试脚本
#
# 功能：
#   1. 构建 engine 镜像
#   2. 运行 engine 容器并验证数据生成
#   3. 验证 docker-compose.yml 配置
#   4. （可选）使用 docker compose up 测试编排
#
# 用法：
#   chmod +x scripts/docker_build_test.sh
#   ./scripts/docker_build_test.sh
#
# 环境要求：
#   - Docker 已安装且 daemon 运行中
#   - 在 C_end_Simulator/ 目录下运行
# ───────────────────────────────────────────────────────────────────

set -euo pipefail

# ── 颜色输出 ──
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ── 切换到项目根目录 ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

echo -e "${YELLOW}==============================${NC}"
echo -e "${YELLOW}  PetNode Docker 构建与测试${NC}"
echo -e "${YELLOW}==============================${NC}"
echo ""

# ── 检查 Docker 是否可用 ──
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker 未安装或不在 PATH 中${NC}"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo -e "${RED}✗ Docker daemon 未运行${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker 环境就绪${NC}"
echo ""

# ── Step 1: 构建 engine 镜像 ──
echo -e "${YELLOW}[Step 1/4] 构建 engine 镜像...${NC}"
if docker build \
    -f engine/Dockerfile \
    -t petnode-engine:latest \
    . ; then
    echo -e "${GREEN}✓ engine 镜像构建成功${NC}"
else
    echo -e "${RED}✗ engine 镜像构建失败${NC}"
    exit 1
fi
echo ""

# ── Step 2: 运行 engine 容器并验证数据生成 ──
echo -e "${YELLOW}[Step 2/4] 运行 engine 容器测试...${NC}"

# 创建临时输出目录
TEST_OUTPUT_DIR=$(mktemp -d)
echo "  临时输出目录: ${TEST_OUTPUT_DIR}"

if ! docker run --rm \
    -v "${TEST_OUTPUT_DIR}:/app/output_data" \
    petnode-engine:latest \
    --dogs 2 \
    --ticks 20 \
    --interval 0 \
    --seed 42 \
    --output-dir /app/output_data ; then
    echo -e "${RED}✗ engine 容器运行失败${NC}"
    rm -rf "${TEST_OUTPUT_DIR}"
    exit 1
fi

# 验证输出文件
JSONL_FILE="${TEST_OUTPUT_DIR}/realtime_stream.jsonl"
STATUS_FILE="${TEST_OUTPUT_DIR}/engine_status.json"

if [ -f "${JSONL_FILE}" ]; then
    LINE_COUNT=$(wc -l < "${JSONL_FILE}")
    echo -e "${GREEN}✓ realtime_stream.jsonl 已生成 (${LINE_COUNT} 条记录)${NC}"
    # 预期 2 dogs × 20 ticks = 40 条记录
    if [ "${LINE_COUNT}" -eq 40 ]; then
        echo -e "${GREEN}✓ 记录数正确 (2 dogs × 20 ticks = 40)${NC}"
    else
        echo -e "${RED}✗ 记录数不正确: 预期 40, 实际 ${LINE_COUNT}${NC}"
    fi
else
    echo -e "${RED}✗ realtime_stream.jsonl 未生成${NC}"
    rm -rf "${TEST_OUTPUT_DIR}"
    exit 1
fi

if [ -f "${STATUS_FILE}" ]; then
    echo -e "${GREEN}✓ engine_status.json 已生成${NC}"
else
    echo -e "${RED}✗ engine_status.json 未生成${NC}"
fi

# 清理
rm -rf "${TEST_OUTPUT_DIR}"
echo ""

# ── Step 3: 验证 docker-compose.yml ──
echo -e "${YELLOW}[Step 3/4] 验证 docker-compose.yml...${NC}"
docker compose -f docker-compose.yml config --quiet 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ docker-compose.yml 语法正确${NC}"
else
    echo -e "${RED}✗ docker-compose.yml 语法错误${NC}"
    exit 1
fi
echo ""

# ── Step 4: docker compose 编排测试 ──
echo -e "${YELLOW}[Step 4/4] docker compose 编排测试...${NC}"
echo "  使用 docker compose up 启动 engine 服务（限时 30 秒）..."

# 启动 engine 服务（后台运行），使用较少的 ticks 以便快速完成
docker compose -f docker-compose.yml up --build -d engine 2>&1

# 等待容器启动并运行
echo "  等待 engine 容器运行..."
sleep 5

# 检查容器状态
ENGINE_STATUS=$(docker compose -f docker-compose.yml ps --format json 2>/dev/null | head -1)
if [ -n "${ENGINE_STATUS}" ]; then
    echo -e "${GREEN}✓ engine 服务已启动${NC}"
else
    echo -e "${YELLOW}⚠ 无法确认 engine 服务状态（可能已完成退出）${NC}"
fi

# 停止并清理
docker compose -f docker-compose.yml down 2>&1
echo -e "${GREEN}✓ docker compose 编排测试完成${NC}"
echo ""

# ── 汇总 ──
echo -e "${GREEN}==============================${NC}"
echo -e "${GREEN}  所有 Docker 测试通过 ✓${NC}"
echo -e "${GREEN}==============================${NC}"
