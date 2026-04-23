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
    git \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv/uvx（MCP stdio 服务器需要 uvx 启动）
RUN pip install --no-cache-dir uv -i https://mirrors.aliyun.com/pypi/simple/

# 创建 uv 配置目录并配置国内镜像（关键修复）
RUN mkdir -p /root/.config/uv && \
    echo '[index]' > /root/.config/uv/uv.toml && \
    echo 'url = "https://mirrors.aliyun.com/pypi/simple/"' >> /root/.config/uv/uv.toml && \
    echo 'default = true' >> /root/.config/uv/uv.toml

# 预安装 MCP 服务器到系统（使用 pip 而非 uv tool）
# 使用不需要 API Key 的 MCP 服务器
RUN pip install --no-cache-dir \
    mcp-server-fetch \
    httpx \
    sse-starlette \
    pydantic \
    -i https://mirrors.aliyun.com/pypi/simple/

# 从构建阶段复制 Python 包
COPY --from=base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

# 先复制不常变化的文件
COPY init_db.py .

# 最后复制应用代码（最常变化的部分）
COPY app ./app

# .env 文件建议通过 docker-compose 的 env_file 或环境变量传入，不要打包到镜像
# COPY .env .

# 创建非 root 用户
RUN useradd -m -u 1000 flowpilot && chown -R flowpilot:flowpilot /app

# 为 flowpilot 用户创建 uv 配置（关键：非 root 用户也需要配置）
RUN mkdir -p /home/flowpilot/.config/uv && \
    echo '[index]' > /home/flowpilot/.config/uv/uv.toml && \
    echo 'url = "https://mirrors.aliyun.com/pypi/simple/"' >> /home/flowpilot/.config/uv/uv.toml && \
    echo 'default = true' >> /home/flowpilot/.config/uv/uv.toml && \
    chown -R flowpilot:flowpilot /home/flowpilot/.config

USER flowpilot

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
