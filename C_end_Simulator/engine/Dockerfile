# ──────────────────────────────────────────────────────────────
# engine/Dockerfile —— 引擎容器镜像构建说明
#
# 用途：
#   将 engine/ 目录下的数据模拟引擎打包成 Docker 镜像，
#   实现"一键运行"的容器化部署。
#
# 构建上下文 (context)：
#   需要在 C_end_Simulator/ 目录下执行构建（因为 COPY 路径相对于 context）
#   - 通过 docker compose build engine 自动构建
#   - 或手动: docker build -f engine/Dockerfile -t petnode-engine .
#
# 运行时数据交互：
#   引擎运行时会将数据写入 /app/output_data/（容器内路径），
#   通过 docker-compose.yml 中的 bind mount 映射到宿主机的 output_data/ 目录，
#   使得 TUI/GUI 可以在宿主机或另一个容器中实时读取引擎输出的数据。
#
# ENTRYPOINT + CMD 设计：
#   - ENTRYPOINT 固定为 python -m engine.main（始终运行引擎主程序）
#   - CMD 提供默认参数（2 只狗 / 200 ticks / 1 秒间隔 / seed=42）
#   - 用户可通过 docker run 或 docker-compose.yml 的 command 字段覆盖 CMD 参数
# ──────────────────────────────────────────────────────────────

# 基础镜像：Python 3.12 精简版（体积小，适合生产部署）
FROM python:3.12-slim

LABEL maintainer="PetNode Team"
LABEL description="PetNode C端 智能项圈数据模拟引擎"

# 设置工作目录（所有后续操作相对于 /app）
WORKDIR /app

# 先复制依赖清单，利用 Docker 缓存层
# 只要 requirements.txt 没变，就不会重新 pip install（加速迭代构建）
COPY engine/requirements.txt /app/engine/requirements.txt
RUN pip install --no-cache-dir -r engine/requirements.txt

# 复制 engine 源码（包括 models/ traits/ events/ exporters/ listeners/ main.py）
COPY engine/ /app/engine/

# 创建输出目录（运行时通过 bind mount 映射到宿主机）
RUN mkdir -p /app/output_data

# 默认入口：启动引擎（可通过 docker-compose 或 docker run 覆盖参数）
# 示例: docker run petnode-engine --dogs 5 --ticks 500 --interval 2
ENTRYPOINT ["python", "-m", "engine.main"]
CMD ["--dogs", "2", "--ticks", "200", "--interval", "1", "--seed", "42", "--output-dir", "/app/output_data"]