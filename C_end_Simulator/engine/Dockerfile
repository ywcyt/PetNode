FROM python:3.12-slim

LABEL maintainer="PetNode Team"
LABEL description="PetNode C端 智能项圈数据模拟引擎"

WORKDIR /app

# 先复制依赖清单，利用 Docker 缓存层
COPY engine/requirements.txt /app/engine/requirements.txt
RUN pip install --no-cache-dir -r engine/requirements.txt

# 复制 engine 源码
COPY engine/ /app/engine/

# 创建输出目录
RUN mkdir -p /app/output_data

# 默认入口：启动引擎（可通过 docker-compose 或 docker run 覆盖参数）
ENTRYPOINT ["python", "-m", "engine.main"]
CMD ["--dogs", "2", "--ticks", "200", "--interval", "1", "--seed", "42", "--output-dir", "/app/output_data"]