# 网络问题修复指南

## 问题：uvx 下载 MCP 服务器超时

### 错误信息
```
error: Request failed after 3 retries in 94.9s
Caused by: Failed to fetch: `https://pypi.org/simple/uvicorn/`
Caused by: error decoding response body
Caused by: operation timed out
```

### 原因
在中国大陆环境中，直接访问 PyPI 官方源速度慢或超时。

---

## 解决方案对比

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| 方案 1：配置镜像源 | 简单快速 | 运行时仍需下载 | ⭐⭐⭐⭐ |
| 方案 2：预安装到镜像 | 启动快 | 镜像体积大 | ⭐⭐⭐⭐⭐ |
| 方案 3：禁用 MCP | 最简单 | 失去 MCP 功能 | ⭐⭐⭐ |

---

## 方案 1：配置国内镜像源（已应用）

### 修改内容

**docker-compose.yml**
```yaml
environment:
  UV_INDEX_URL: https://mirrors.aliyun.com/pypi/simple/
  UV_EXTRA_INDEX_URL: https://pypi.org/simple/
```

### 应用修改
```bash
docker-compose down
docker-compose up -d
```

### 验证
```bash
docker logs flow_pilot_app --tail 50
# 应该看到成功下载 MCP 服务器
```

---

## 方案 2：预安装 MCP 服务器（已应用）

### 修改内容

**Dockerfile**
```dockerfile
# 配置 uv 使用国内镜像并预安装 MCP 服务器
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
RUN uv tool install mcp-server-weather --python /usr/local/bin/python3.11
```

### 应用修改
```bash
# 重新构建镜像
docker-compose build --no-cache app
docker-compose up -d
```

### 优点
- MCP 服务器打包在镜像中
- 启动时无需下载
- 离线环境也能使用

---

## 方案 3：完全禁用 MCP

如果暂时不需要 MCP 功能：

**docker-compose.yml**
```yaml
environment:
  MCP_SERVERS_JSON: '{}'  # 空配置
```

或在 `.env` 文件中：
```bash
MCP_SERVERS_JSON='{}'
```

---

## 其他镜像源选项

### 清华大学镜像
```yaml
UV_INDEX_URL: https://pypi.tuna.tsinghua.edu.cn/simple/
```

### 中科大镜像
```yaml
UV_INDEX_URL: https://pypi.mirrors.ustc.edu.cn/simple/
```

### 腾讯云镜像
```yaml
UV_INDEX_URL: https://mirrors.cloud.tencent.com/pypi/simple/
```

### 华为云镜像
```yaml
UV_INDEX_URL: https://repo.huaweicloud.com/repository/pypi/simple/
```

---

## 测试网络连接

### 测试 PyPI 连接
```bash
# 在容器内测试
docker-compose exec app curl -I https://pypi.org/simple/

# 测试国内镜像
docker-compose exec app curl -I https://mirrors.aliyun.com/pypi/simple/
```

### 测试 DNS 解析
```bash
docker-compose exec app nslookup pypi.org
docker-compose exec app nslookup mirrors.aliyun.com
```

### 配置 Docker DNS
如果 DNS 解析有问题，在 `docker-compose.yml` 中添加：

```yaml
services:
  app:
    dns:
      - 223.5.5.5      # 阿里 DNS
      - 114.114.114.114 # 114 DNS
      - 8.8.8.8        # Google DNS
```

---

## 代理配置（可选）

如果有 HTTP 代理：

**docker-compose.yml**
```yaml
services:
  app:
    environment:
      HTTP_PROXY: http://proxy.example.com:8080
      HTTPS_PROXY: http://proxy.example.com:8080
      NO_PROXY: localhost,127.0.0.1,redis,postgres,milvus
```

---

## 完整修复流程

### 1. 应用所有修复
```bash
cd ~/Flow-Pilot

# 停止容器
docker-compose down

# 重新构建（应用 Dockerfile 更改）
docker-compose build --no-cache app

# 启动
docker-compose up -d
```

### 2. 监控启动过程
```bash
# 实时查看日志
docker logs flow_pilot_app -f

# 等待看到这些信息：
# ✅ [Redis] 连接成功
# ✅ [Milvus] 连接成功
# ✅ Flow-Pilot 启动完成
```

### 3. 验证 MCP 服务器
```bash
# 检查 MCP 工具
curl http://localhost:8000/api/v1/tools/ | python3 -m json.tool

# 应该看到 weather 工具列表
```

### 4. 测试前端
```bash
# 启动前端
cd frontend
python3 -m http.server 8080 --bind 0.0.0.0

# 访问 http://<虚拟机IP>:8080
```

---

## 自动化脚本

使用提供的快速修复脚本：

```bash
chmod +x quick-fix.sh
./quick-fix.sh
```

脚本会自动：
1. 停止容器
2. 重新构建镜像
3. 启动服务
4. 检查状态
5. 显示访问地址

---

## 故障排查

### 问题：构建时仍然超时

**解决**：使用更快的镜像源
```bash
# 编辑 Dockerfile，替换镜像源
sed -i 's|mirrors.aliyun.com|pypi.tuna.tsinghua.edu.cn|g' Dockerfile
docker-compose build --no-cache app
```

### 问题：MCP 服务器安装失败

**解决**：跳过预安装，使用运行时下载
```dockerfile
# Dockerfile 中改为
RUN uv tool install mcp-server-weather --python /usr/local/bin/python3.11 || echo "Skipped"
```

### 问题：容器启动后立即退出

**查看日志**：
```bash
docker logs flow_pilot_app
docker-compose logs app
```

**常见原因**：
- 数据库连接失败
- 环境变量配置错误
- 端口冲突

---

## 性能优化

### 使用 Docker BuildKit
```bash
export DOCKER_BUILDKIT=1
docker-compose build
```

### 并行构建
```bash
docker-compose build --parallel
```

### 清理缓存
```bash
docker builder prune -a
```

---

## 验证清单

- [ ] 容器正常运行：`docker-compose ps`
- [ ] 后端健康检查通过：`curl http://localhost:8000/health`
- [ ] Redis 连接成功（日志中显示）
- [ ] Milvus 连接成功（日志中显示）
- [ ] MCP 服务器加载成功（无错误日志）
- [ ] 前端可以访问后端 API
- [ ] 系统状态显示正常

---

## 获取帮助

如果问题仍未解决，请提供：

1. **完整日志**
   ```bash
   docker logs flow_pilot_app > app.log
   ```

2. **网络测试结果**
   ```bash
   docker-compose exec app curl -v https://mirrors.aliyun.com/pypi/simple/
   ```

3. **系统信息**
   ```bash
   docker --version
   docker-compose --version
   uname -a
   ```
