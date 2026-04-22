# Flow-Pilot —— 基于MCP协议与反思工作流的异构任务编排Agent框架实战

## 1. 项目概述

**Flow-Pilot** 是一款先进的任务编排 Agent 框架，旨在通过 **MCP (Model Context Protocol)** 协议与 **Reflexion (反思)** 工作流，实现对复杂、异构任务的自动化处理。本项目采用 **LangGraph** 进行状态管理，并使用 **FastAPI** 提供高性能的后端服务。

## 2. 核心架构设计

- **编排层 (Orchestration Layer)**: 基于 **LangGraph** 的状态机架构，支持任务的动态拆解、意图对齐及状态流转。
- **协议层 (Protocol Layer)**: 引入 **MCP** 协议，标准化异构工具（本地脚本、API、数据库等）的调用链路，实现工具的即插即用。
- **记忆层 (Memory Layer)**:
  - **Redis**: 负责短期上下文缓存、会话管理。
  - **Milvus**: 负责长期向量记忆（RAG），支持历史经验的检索与复用。
- **工作流模式 (Workflow Pattern)**: 深度集成 **Reflexion** 机制（Plan -> Execute -> Critic -> Re-plan），构建具备自我纠错能力的闭环系统。

## 3. 技术栈

- **语言**: Python 3.10+
- **API 框架**: FastAPI
- **Agent 编排**: LangGraph / LangChain
- **协议标准**: MCP (Model Context Protocol)
- **向量数据库**: Milvus
- **缓存/Session**: Redis
- **LLM 适配**: LiteLLM (支持 OpenAI, DeepSeek, Anthropic 等多模型切换)
- **状态持久化**: PostgreSQL (用于 LangGraph Checkpoints)

## 4. 模块化分解

- `app/api/`: 存放 FastAPI 路由、Request/Response Schema。
- `app/engine/`: 定义 LangGraph 状态机、节点逻辑与连边规则。
- `app/mcp/`: MCP Client 实现，负责工具注册与调用分发。
- `app/memory/`: 封装 Redis 与 Milvus 的读写接口。
- `app/agents/`: 定义具体 Agent 角色（如 Planner, Executor, Critic）。
- `app/core/`: 项目基础配置、工具类及日志管理。

## 5. 实施路线图

### 第一阶段：基础设施搭建 (MVP)

- 搭建 FastAPI 项目骨架，配置异步环境。
- 集成 LangGraph，实现基础的“规划-执行”状态机。
- 引入 PostgreSQL 进行图状态的持久化存储。

### 第二阶段：工具集成与协议标准化

- 实现 MCP Client，对接外部工具服务器。
- 使用 Pydantic 标准化工具输入输出 Schema。
- 实现工具的动态发现与按需调用。

### 第三阶段：分层记忆与上下文管理

- 集成 Redis 实现会话级别的上下文快速缓存。
- 集成 Milvus 构建语义记忆库，支持长程依赖任务。
- 开发上下文压缩与修剪算法，提升长对话下的模型鲁棒性。

### 第四阶段：反思机制与执行优化

- 在 LangGraph 中加入 "Critic" 反思节点。
- 实现完整的 Reflexion 闭环，支持对执行失败的任务进行自动重试与方案修正。
- 优化 Prompt Template，提升复杂意图下的指令对齐准确度。

### 第五阶段：工程化交付与展示

- 完成 Docker + Docker Compose 容器化部署。
- 开发简单的 Gradio 或 Streamlit 前端 Demo 界面。
- 集成 LangSmith 或 Helicone 提升链路追踪与可观测性。

## 6. 测试与验证

- **单元测试**: 覆盖核心 Agent 逻辑与独立工具函数。
- **集成测试**: 验证 MCP 协议下工具调用的稳定性。
- **全链路测试**: 模拟真实业务场景，测试“需求->规划->执行->反思->交付”的完整闭环。
- **性能分析**: 监控各环节耗时及 Token 消耗，针对性优化。

## 7. 第二阶段（真实 MCP）验收建议

为避免仅通过 Mock 测试导致“已实现但未真实连通”，建议执行以下验收：

1. 在 `.env` 中配置 `MCP_SERVERS_JSON`（至少 1 个真实服务器）。
2. 运行真实集成测试脚本：

```bash
python test/test_mcp_integration.py
```

3. 若需验证真实工具调用，在运行前设置：

```bash
# 示例（按实际工具名称与参数替换）
set MCP_TEST_TOOL_NAME=get_weather
set MCP_TEST_TOOL_ARGS_JSON={"city":"tokyo"}
python test/test_mcp_integration.py
```

通过标准：
- 成功发现至少 1 个 MCP 工具；
- 指定工具调用成功（可选但推荐）。
