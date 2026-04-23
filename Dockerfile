# ── 第一阶段：构建基础镜像 ──────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN sed -i "s@http://deb.debian.org@https://mirrors.tuna.tsinghua.edu.cn@g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y \
        gcc \
        g++ \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/ && \
    pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# ── 第二阶段：运行镜像 ────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# 安装运行时依赖
RUN sed -i "s@http://deb.debian.org@https://mirrors.tuna.tsinghua.edu.cn@g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv/uvx（MCP stdio 服务器需要 uvx 启动）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=ghcr.io/astral-sh/uv:latest /uvx /usr/local/bin/uvx

# 从构建阶段复制 Python 包
COPY --from=base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

# 复制应用代码
COPY app ./app
COPY init_db.py .
COPY .env .

# 创建非 root 用户
RUN useradd -m -u 1000 flowpilot && chown -R flowpilot:flowpilot /app
USER flowpilot

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
