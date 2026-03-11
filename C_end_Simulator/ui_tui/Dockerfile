FROM python:3.12-slim

LABEL maintainer="PetNode Team"
LABEL description="PetNode C端 TUI 终端监控界面"

WORKDIR /app

# 先复制依赖清单，利用 Docker 缓存层
COPY ui_tui/requirements.txt /app/ui_tui/requirements.txt
RUN pip install --no-cache-dir -r ui_tui/requirements.txt

# 复制 TUI 源码
COPY ui_tui/ /app/ui_tui/

# 默认入口
ENTRYPOINT ["python", "-m", "ui_tui.app"]