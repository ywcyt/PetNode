# ──────────────────────────────────────────────────────────────
# ui_tui/Dockerfile —— TUI 终端界面容器镜像构建说明
#
# 用途：
#   将 ui_tui/ 目录下的 PetNodeOS 终端界面打包成 Docker 镜像。
#   这是将 TUI 封装进 Docker 的关键——通过 Textual 框架实现纯终端渲染，
#   无需图形环境，因此可以在 Docker 容器中运行。
#
# TUI 如何在 Docker 中工作：
#   1. Textual 框架使用终端转义序列 (ANSI escape codes) 渲染 UI
#   2. Docker 通过 stdin_open: true + tty: true 分配伪终端 (PTY)
#   3. 用户通过 docker compose run --rm tui 以交互模式连接到容器的 TTY
#   4. Textual 在容器内的 PTY 上渲染全屏终端界面，用户在宿主机终端中操作
#   → 效果：用户看到的是一个全屏终端应用，但实际运行在 Docker 容器内
#
# 与 Engine 的通信：
#   TUI 通过 output_data/ bind mount 共享卷与 Engine 容器通信：
#   - 读取 engine_status.json 和 realtime_stream.jsonl（由 Engine 写入）
#   - 写入 command.json（由 Engine 轮询读取）
#
# 构建上下文 (context)：
#   与 Engine 相同，需要在 C_end_Simulator/ 目录下执行构建
#   - 通过 docker compose --profile tui build 自动构建
#   - 启动: docker compose --profile tui run --rm tui
# ──────────────────────────────────────────────────────────────

# 基础镜像：Python 3.12 精简版
FROM python:3.12-slim

LABEL maintainer="PetNode Team"
LABEL description="PetNodeOS TUI 终端监控界面"

# 设置工作目录
WORKDIR /app

# 先复制依赖清单，利用 Docker 缓存层
# TUI 依赖 textual 框架（纯终端 UI 库，无需图形环境）
COPY ui_tui/requirements.txt /app/ui_tui/requirements.txt
RUN pip install --no-cache-dir -r ui_tui/requirements.txt

# 复制 TUI 源码（含 backend/ 后端接口层和 screens/ 前端界面层）
COPY ui_tui/ /app/ui_tui/

# 默认入口：启动 TUI 应用，指定数据目录为 Docker bind mount 路径
ENTRYPOINT ["python", "-m", "ui_tui.app"]
CMD ["--output-dir", "/app/output_data"]