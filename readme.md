# Flow-Pilot

基于 MCP 协议与 Reflexion 工作流的异构任务编排 Agent 框架。

## 核心特性

- **MCP 协议**：标准化工具调用，支持 stdio/sse 两种传输方式
- **Reflexion 闭环**：Plan → Execute → Critic → Re-plan 自我纠错
- **分层记忆**：Redis 短期缓存 + Milvus 长期向量记忆
- **LangGraph**：基于状态机的可持久化工作流
- **流式输出**：SSE 实时推送执行过程
- **前端 Demo**：开箱即用的静态页面，支持任务提交与状态监控

## 技术栈

- **后端**：Python 3.11, FastAPI, LangGraph, LangChain
- **Agent 编排**：Planner / Executor / Critic 三角色协作
- **协议**：MCP (Model Context Protocol)
- **记忆**：Redis (短期), Milvus (长期向量)
- **持久化**：PostgreSQL (LangGraph Checkpoints)
- **LLM**：LiteLLM (支持 OpenAI, DeepSeek, SiliconFlow 等)
- **前端**：原生 HTML + JavaScript

## 快速开始

### 环境准备

1. 安装 Python 3.11+
2. 安装 Docker + Docker Compose（用于依赖服务）
3. 复制环境配置：

```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM API Key
```

### 启动依赖服务

```bash
docker-compose up -d postgres redis milvus
```

> 首次启动 Milvus 可能需要等待 etcd + minio 就绪。

### 启动后端

```bash
pip install -r requirements.txt
python app/main.py
```

后端运行在 `http://127.0.0.1:8000`

### 启动前端

```bash
cd frontend
python -m http.server 8080
```

浏览器访问 `http://localhost:8080`

> 也可以直接双击打开 `frontend/index.html`。

---

## Docker 全栈部署

一键启动所有服务（含后端、前端代理可通过 8000 访问 API）：

```bash
docker-compose up -d
```

容器说明：

| 容器 | 服务 | 端口 |
|------|------|------|
| flow_pilot_postgres | PostgreSQL | 5432 |
| flow_pilot_redis | Redis | 6379 |
| flow_pilot_milvus | Milvus | 19530 |
| flow_pilot_app | Flow-Pilot 后端 | 8000 |

---

## 项目结构

```
.
├── app/
│   ├── api/              # FastAPI 路由 (tasks, tools)
│   ├── engine/           # LangGraph 状态机与节点
│   ├── agents/           # Planner, Executor, Critic
│   ├── core/             # 配置, LLM 封装, 日志
│   ├── mcp/              # MCP 客户端与管理器
│   └── memory/           # Redis / Milvus / ContextManager
├── frontend/             # 前端 Demo (HTML + JS)
├── test/                 # 测试脚本
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── init_db.py
```

---

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查（Redis/Milvus/MCP 状态） |
| GET | `/metrics` | LLM Token 使用统计 |
| POST | `/api/v1/tasks/` | 提交任务（支持 `stream=true` SSE） |
| GET | `/api/v1/tasks/{thread_id}` | 获取任务历史 |
| GET | `/api/v1/tasks/` | 列出会话 ID |
| GET | `/api/v1/tools/` | 获取可用工具列表 |
| GET | `/api/v1/tools/{tool_name}` | 获取工具详情 |
| POST | `/api/v1/tools/{tool_name}/call` | 直接调用工具（调试） |
| GET | `/api/v1/tools/servers/status` | MCP 服务器连接状态 |

完整文档：`http://127.0.0.1:8000/docs`

---

## 测试

### 宿主机运行（推荐）

确保依赖服务已启动，且 `.env` 中的数据库连接指向 `localhost`：

```bash
# 全链路 + Reflexion 闭环
python test/test_graph.py

# ReAct 工具调用闭环
python test/test_react_loop.py

# 真实 MCP 集成验证
python test/test_mcp_integration.py

# 指定工具进行真实调用
set MCP_TEST_TOOL_NAME=get_weather
set MCP_TEST_TOOL_ARGS_JSON={"city":"tokyo"}
python test/test_mcp_integration.py
```

### 容器内运行

当前镜像未包含 `test/` 目录，需要手动复制：

```bash
docker cp test flow_pilot_app:/app/test
docker exec -it flow_pilot_app python test/test_graph.py
```

---

## 配置说明

关键环境变量（`.env`）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SILICONFLOW_API_KEY` | LLM API Key | - |
| `SILICONFLOW_MODEL` | 模型名称 | `deepseek-ai/DeepSeek-V3` |
| `DATABASE_URL` | PostgreSQL 连接 | - |
| `REDIS_URL` | Redis 连接 | `redis://localhost:6379/0` |
| `MILVUS_HOST` | Milvus 地址 | `localhost` |
| `MCP_SERVERS_JSON` | MCP 服务器配置 | `{}` |
| `MAX_REFLECTION_ROUNDS` | 最大反思轮次 | `3` |
| `REFLECTION_SCORE_THRESHOLD` | 反思评分阈值 | `0.7` |

---

## MCP 服务器配置示例

在 `.env` 中设置 `MCP_SERVERS_JSON`：

```env
# stdio 方式
MCP_SERVERS_JSON='{"weather":{"type":"stdio","command":"uvx","args":["mcp-server-weather"]}}'

# sse 方式
MCP_SERVERS_JSON='{"remote":{"type":"sse","url":"http://127.0.0.1:8001/sse"}}'
```
