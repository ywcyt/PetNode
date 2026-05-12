# ──────────────────────────────────────────────────────────────
# ui_tui/Dockerfile —— TUI 终端监控界面容器镜像
#
# 用途：
#   将 ui_tui/ 目录下的 TUI 应用打包成 Docker 镜像，
#   通过 docker compose --profile tui run --rm tui 交互式启动。
#
# 构建上下文 (context)：
#   需要在 C_end_Simulator/ 目录下执行构建
# ──────────────────────────────────────────────────────────────

FROM python:3.12-slim

LABEL maintainer="PetNode Team"
LABEL description="PetNode C端 TUI 终端监控界面"

WORKDIR /app

# 先复制依赖清单（利用 Docker 缓存层加速构建）
COPY ui_tui/requirements.txt /app/ui_tui/requirements.txt
RUN pip install --no-cache-dir -r ui_tui/requirements.txt

# 复制 ui_tui 源码
COPY ui_tui/ /app/ui_tui/

ENTRYPOINT ["python", "-m", "ui_tui.app"]
CMD ["--output-dir", "/app/output_data"]
