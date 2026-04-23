# 故障排查指南

## 问题 1：前端显示"连接失败"

### 症状
- Docker 容器正常运行
- 前端页面显示"系统状态：连接失败"

### 原因
前端 JavaScript 尝试连接 `http://127.0.0.1:8000`，但在虚拟机或远程环境中，需要使用实际的 IP 地址。

### 解决方案

**方案 1：自动检测（已修复）**

前端代码已更新为自动使用当前主机名：
```javascript
const API_BASE = `${window.location.protocol}//${window.location.hostname}:8000/api/v1`;
```

**方案 2：手动配置**

如果自动检测不工作，可以手动修改 `frontend/app.js`：
```javascript
// 替换为你的虚拟机 IP
const API_BASE = 'http://192.168.56.101:8000/api/v1';
```

**方案 3：使用端口转发**

在 VirtualBox 中设置端口转发：
1. 虚拟机设置 → 网络 → 高级 → 端口转发
2. 添加规则：主机端口 8000 → 虚拟机端口 8000
3. 前端访问 `http://localhost:8000`

### 验证

```bash
# 在虚拟机中测试后端是否正常
curl http://localhost:8000/health

# 在宿主机中测试（替换为虚拟机 IP）
curl http://192.168.56.101:8000/health
```

---

## 问题 2：MCP Git 服务器错误

### 症状
```
ERROR:mcp_server_git.server:. is not a valid Git repository
```

### 原因
Docker 容器内没有 `.git` 目录，但 MCP 配置中启用了 git 服务器。

### 解决方案

**方案 1：禁用 git 服务器（推荐）**

在 `docker-compose.yml` 中已配置：
```yaml
environment:
  MCP_SERVERS_JSON: '{"weather":{"type":"stdio","command":"uvx","args":["mcp-server-weather"]}}'
```

**方案 2：挂载 .git 目录**

如果需要 git 功能，在 `docker-compose.yml` 中取消注释：
```yaml
volumes:
  - ./.git:/app/.git:ro
```

然后重启：
```bash
docker-compose down
docker-compose up -d
```

**方案 3：本地运行（不使用 Docker）**

```bash
# 只启动依赖服务
docker-compose up postgres redis etcd minio milvus -d

# 本地运行应用（保留 .git 目录）
python app/main.py
```

---

## 问题 3：容器启动失败

### 检查容器状态

```bash
# 查看所有容器
docker-compose ps

# 查看失败容器的日志
docker-compose logs app
docker-compose logs postgres
docker-compose logs milvus
```

### 常见原因

**端口冲突**
```bash
# 检查端口占用
sudo netstat -tulpn | grep :8000
sudo netstat -tulpn | grep :5432

# 修改 docker-compose.yml 中的端口
ports:
  - "8001:8000"  # 使用不同的宿主机端口
```

**内存不足**
```bash
# 检查 Docker 资源
docker stats

# 增加 Docker 内存限制（Docker Desktop）
# 设置 → Resources → Memory: 4GB+
```

**依赖服务未就绪**
```bash
# 等待所有服务健康
docker-compose ps

# 手动重启应用
docker-compose restart app
```

---

## 问题 4：Milvus 连接失败

### 症状
```
[Milvus] 连接失败，使用内存回退模式
```

### 原因
Milvus 启动较慢（依赖 etcd 和 minio），可能需要 1-2 分钟。

### 解决方案

```bash
# 检查 Milvus 状态
docker-compose logs milvus

# 等待 Milvus 健康
docker-compose ps milvus

# 重启应用（Milvus 就绪后）
docker-compose restart app
```

---

## 问题 5：CORS 错误

### 症状
浏览器控制台显示：
```
Access to fetch at 'http://...' from origin 'http://...' has been blocked by CORS policy
```

### 解决方案

在 `.env` 中设置：
```bash
CORS_ORIGINS="*"  # 开发环境
# 或指定具体域名
CORS_ORIGINS="http://localhost:8080,http://192.168.56.101:8080"
```

重启容器：
```bash
docker-compose restart app
```

---

## 问题 6：前端无法访问

### 症状
`python -m http.server 8080` 启动后，浏览器无法访问。

### 解决方案

**绑定到所有接口**
```bash
# 默认只监听 localhost
python -m http.server 8080

# 监听所有接口（允许外部访问）
python -m http.server 8080 --bind 0.0.0.0
```

**检查防火墙**
```bash
# Ubuntu/Debian
sudo ufw status
sudo ufw allow 8080

# CentOS/RHEL
sudo firewall-cmd --add-port=8080/tcp --permanent
sudo firewall-cmd --reload
```

---

## 问题 7：数据库连接失败

### 症状
```
sqlalchemy.exc.OperationalError: could not connect to server
```

### 解决方案

```bash
# 检查 PostgreSQL 状态
docker-compose logs postgres

# 测试连接
docker-compose exec postgres psql -U postgres -d flow_pilot

# 重新初始化数据库
docker-compose exec app python init_db.py
```

---

## 调试技巧

### 1. 查看实时日志
```bash
# 所有服务
docker-compose logs -f

# 特定服务
docker-compose logs -f app
```

### 2. 进入容器调试
```bash
# 进入应用容器
docker-compose exec app bash

# 测试网络连接
docker-compose exec app curl http://postgres:5432
docker-compose exec app curl http://redis:6379
```

### 3. 检查环境变量
```bash
docker-compose exec app env | grep -E "DATABASE|REDIS|MILVUS"
```

### 4. 重建容器
```bash
# 停止并删除容器
docker-compose down

# 重新构建并启动
docker-compose up -d --build
```

### 5. 完全清理
```bash
# ⚠️ 警告：会删除所有数据
docker-compose down -v
docker system prune -a
docker-compose up -d --build
```

---

## 快速诊断脚本

创建 `check.sh`：
```bash
#!/bin/bash

echo "=== Docker 容器状态 ==="
docker-compose ps

echo -e "\n=== 后端健康检查 ==="
curl -s http://localhost:8000/health | jq .

echo -e "\n=== PostgreSQL 连接 ==="
docker-compose exec -T postgres pg_isready -U postgres

echo -e "\n=== Redis 连接 ==="
docker-compose exec -T redis redis-cli ping

echo -e "\n=== Milvus 连接 ==="
curl -s http://localhost:9091/healthz

echo -e "\n=== 应用日志（最后 10 行）==="
docker-compose logs --tail=10 app
```

运行：
```bash
chmod +x check.sh
./check.sh
```

---

## 获取帮助

如果以上方法都无法解决问题，请提供以下信息：

1. **系统信息**
   ```bash
   uname -a
   docker --version
   docker-compose --version
   ```

2. **容器状态**
   ```bash
   docker-compose ps
   ```

3. **完整日志**
   ```bash
   docker-compose logs > logs.txt
   ```

4. **错误截图**
   - 浏览器控制台错误
   - 前端页面截图
