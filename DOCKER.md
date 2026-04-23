# Docker 部署指南

## 问题：为什么每次修改代码都要重新构建？

### 原因

Docker 的**层缓存机制**：
- 每个 `COPY`、`RUN` 等指令都会创建一个层
- 当某层内容变化时，该层及之后的所有层都会失效
- 如果 `COPY app ./app` 在依赖安装之后，修改代码会导致后续层全部重建

### 解决方案

我们采用了以下优化：

1. **调整 Dockerfile 层顺序**：先复制不常变化的文件，最后复制应用代码
2. **使用 Volume 挂载**：开发环境直接挂载代码目录，无需重建镜像
3. **添加 .dockerignore**：减少构建上下文大小
4. **分离开发/生产配置**：不同环境使用不同的 docker-compose 配置

## 快速开始

### 开发环境（推荐）

```bash
# 首次启动（会构建镜像）
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# 后续启动（代码修改会自动热重载，无需重建）
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# 停止
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down
```

**特性**：
- ✅ 代码热重载（修改代码自动生效）
- ✅ 详细日志输出
- ✅ 无需重建镜像

### 生产环境

```bash
# 构建并启动
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 查看日志
docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f app

# 停止
docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
```

**特性**：
- ✅ 多进程部署（4 workers）
- ✅ 资源限制
- ✅ 代码打包到镜像（不依赖外部文件）

### 仅启动依赖服务

如果你想在本地运行 Python 代码，只启动数据库等依赖：

```bash
# 只启动 PostgreSQL, Redis, Milvus
docker-compose up postgres redis etcd minio milvus

# 本地运行应用
python app/main.py
```

## 常用命令

### 查看服务状态

```bash
docker-compose ps
```

### 查看日志

```bash
# 所有服务
docker-compose logs -f

# 特定服务
docker-compose logs -f app
docker-compose logs -f postgres
```

### 重建特定服务

```bash
# 只重建 app 服务
docker-compose up -d --build app
```

### 进入容器

```bash
# 进入应用容器
docker-compose exec app bash

# 进入 PostgreSQL
docker-compose exec postgres psql -U postgres -d flow_pilot

# 进入 Redis
docker-compose exec redis redis-cli
```

### 清理

```bash
# 停止并删除容器
docker-compose down

# 同时删除数据卷（⚠️ 会丢失数据）
docker-compose down -v

# 清理未使用的镜像
docker image prune -a
```

## 优化技巧

### 1. 使用 BuildKit（更快的构建）

```bash
# Linux/Mac
export DOCKER_BUILDKIT=1
docker-compose build

# Windows PowerShell
$env:DOCKER_BUILDKIT=1
docker-compose build
```

### 2. 并行构建

```bash
docker-compose build --parallel
```

### 3. 查看镜像层

```bash
docker history flow_pilot_app
```

### 4. 缓存调试

```bash
# 强制不使用缓存
docker-compose build --no-cache

# 查看构建过程
docker-compose build --progress=plain
```

## 文件说明

- `Dockerfile` - 多阶段构建，优化层缓存
- `docker-compose.yml` - 基础配置（所有环境共用）
- `docker-compose.dev.yml` - 开发环境覆盖配置
- `docker-compose.prod.yml` - 生产环境覆盖配置
- `.dockerignore` - 排除不需要的文件，加速构建

## 故障排查

### 端口冲突

```bash
# 查看端口占用
netstat -ano | findstr :8000
netstat -ano | findstr :5432

# 修改 docker-compose.yml 中的端口映射
ports:
  - "8001:8000"  # 宿主机:容器
```

### 健康检查失败

```bash
# 查看健康状态
docker-compose ps

# 手动测试健康检查
docker-compose exec app curl http://localhost:8000/health
```

### 依赖安装失败

```bash
# 使用国内镜像源（已在 Dockerfile 中配置）
# 如果仍然失败，尝试：
docker-compose build --no-cache
```

### Milvus 启动慢

Milvus 依赖 etcd 和 minio，首次启动需要 1-2 分钟。查看日志：

```bash
docker-compose logs -f milvus
```

## 性能对比

| 场景 | 传统方式 | 优化后 |
|------|---------|--------|
| 首次构建 | ~5 分钟 | ~5 分钟 |
| 修改代码后重建 | ~5 分钟 | **0 秒**（开发环境） |
| 修改依赖后重建 | ~5 分钟 | ~2 分钟（缓存基础层） |

## 最佳实践

1. **开发时使用 dev 配置**：代码挂载 + 热重载
2. **生产前测试 prod 配置**：确保镜像完整性
3. **定期清理**：`docker system prune -a` 释放空间
4. **使用 .env 文件**：不要把敏感信息写入 Dockerfile
5. **监控资源**：`docker stats` 查看容器资源使用

## 参考资料

- [Docker 最佳实践](https://docs.docker.com/develop/dev-best-practices/)
- [Docker Compose 文档](https://docs.docker.com/compose/)
- [多阶段构建](https://docs.docker.com/build/building/multi-stage/)
