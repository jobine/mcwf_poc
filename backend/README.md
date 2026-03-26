# MCWF PoC — Backend

MCWF（MetaCreate Workflow）概念验证后端，将 **ANSA**（FEA 前处理工具）与基于 **LangGraph** 的智能体工作流系统集成。通过 IAP（Inter-ANSA Protocol）协议与 ANSA 进程通信，并以 **FastAPI REST + WebSocket** 接口实时推送工作流执行状态。

## 目录

- [项目结构](#项目结构)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [环境变量](#环境变量)
- [API 接口](#api-接口)
- [架构概览](#架构概览)
- [核心模块](#核心模块)
- [测试](#测试)

## 项目结构

```
backend/
├── app/
│   ├── api/            # FastAPI 路由（REST + WebSocket 端点）
│   ├── agents/         # LangGraph 智能体节点（ANSA 操作）
│   ├── core/           # ANSA 后端核心 & 项目管理
│   ├── graph/          # LangGraph 工作流定义
│   └── config.py       # 集中配置（Pydantic Settings）
├── scripts/            # ANSA Python 脚本（零件分类等）
├── tests/              # 单元测试
├── data/
│   └── shared/         # 共享模型文件（demo.ansa）
├── experiments/        # 运行时实验输出
├── .env.example        # 环境变量模板
└── pyproject.toml      # 项目依赖 & 元数据
```

## 技术栈

| 组件 | 版本要求 |
|------|---------|
| Python | ≥ 3.12, < 4.0 |
| FastAPI | ≥ 0.115.0 |
| Uvicorn | ≥ 0.34.0 |
| LangChain | ≥ 1.2.13 |
| LangGraph | ≥ 1.1.3 |
| LangChain-OpenAI | ≥ 1.1.11 |
| Pydantic Settings | ≥ 2.0.0 |

构建工具：**Poetry**（poetry-core ≥ 2.0.0）

## 快速开始

### 前置条件

- Python 3.12+
- [Poetry](https://python-poetry.org/) 包管理器
- ANSA 已安装并设置 `ANSA_HOME` 环境变量

### 安装依赖

```bash
cd backend
poetry install
```

### 配置

在 `backend/` 目录下创建 `.env` 文件：

```ini
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key_here
LANGCHAIN_PROJECT=mcwf_poc
HOST=0.0.0.0
PORT=8000
```

### 启动服务

```bash
poetry run uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

服务启动后：

- Swagger UI：`http://localhost:8000/docs`
- REST 端点：`POST /experiment`、`GET /experiment/{id}`
- WebSocket 端点：`ws://localhost:8000/experiment/{id}/stdout`

### 独立运行工作流

```bash
poetry run python -m app.graph.workflow
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOST` | `0.0.0.0` | 服务监听地址 |
| `PORT` | `8000` | 服务监听端口 |
| `EXPERIMENTS_DIR` | `experiments` | 实验输出目录 |
| `SCRIPTS_DIR` | `scripts` | ANSA 脚本目录 |
| `DATA_SHARED_DIR` | `data/shared` | 共享模型数据目录 |
| `LANGCHAIN_TRACING_V2` | – | 启用 LangSmith 追踪 |
| `LANGCHAIN_API_KEY` | – | LangSmith API 密钥 |
| `LANGCHAIN_PROJECT` | `mcwf_poc` | LangSmith 项目名称 |
| `ANSA_HOME` | – | ANSA 安装路径 |

## API 接口

采用 REST + WebSocket 两阶段架构：先通过 HTTP 启动工作流，再通过 WebSocket 实时接收输出。

### `POST /experiment`

启动 ANSA 工作流（后台异步执行），立即返回 `experiment_id`。

- **响应 202**：`{"experiment_id": "<uuid>"}`

### `GET /experiment/{experiment_id}`

轮询工作流最终结果。

- **响应 200**：工作流完成，返回最终状态 JSON
- **响应 202**：工作流仍在运行，`{"status": "running"}`
- **响应 404**：未知的 `experiment_id`

### `WS /experiment/{experiment_id}/stdout`

实时流式推送 ANSA 标准输出（含 15 秒心跳保活）。

**服务端 → 客户端消息**（JSON 格式 `{"event": ..., "data": ...}`）：

| 事件 | 说明 |
|------|------|
| `stdout` | ANSA 实时输出行 |
| `heartbeat` | 心跳保活 |
| `done` | 工作流完成，返回最终状态 |
| `error` | 不可恢复的错误信息 |

**客户端 → 服务端消息**（预留，暂未实现）：

| 动作 | 说明 |
|------|------|
| `cancel` | 请求优雅取消 |
| `input` | Human-in-the-loop 回复 |

**客户端示例（JavaScript）：**

```javascript
// 1. 启动工作流
const resp = await fetch("/experiment", { method: "POST" });
const { experiment_id } = await resp.json();

// 2. 连接 stdout 流
const ws = new WebSocket(`ws://host/experiment/${experiment_id}/stdout`);
ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.event === "stdout") console.log(msg.data);
    if (msg.event === "done")  { console.log(msg.data); ws.close(); }
};
```

## 架构概览

```
┌──────────────────────────────────────────────┐
│           FastAPI Server (:8000)              │
│  POST /experiment          → 启动工作流       │
│  GET  /experiment/{id}     → 轮询结果         │
│  WS   /experiment/{id}/stdout → 实时输出流    │
└──────────────────┬───────────────────────────┘
                   ↓
┌──────────────────────────────────────────────┐
│       LangGraph Workflow (graph/)            │
│  START → init_experiment → validate_inputs   │
│        → run_ansa → save_results → END       │
└──────────────────┬───────────────────────────┘
                   ↓
┌──────────────────────────────────────────────┐
│       ANSA Backend (core/ansa_backend.py)    │
│  AnsaProcess                                 │
│  ├─ IAP Connection (TCP Socket)              │
│  ├─ Stdout Reader (异步线程)                  │
│  └─ Script Execution (参数注入)               │
└──────────────────┬───────────────────────────┘
                   ↓
┌──────────────────────────────────────────────┐
│          ANSA (FEA Pre-processor)            │
│  模型加载 · 脚本执行 · 网格操作 · 导出         │
└──────────────────────────────────────────────┘

输出: experiments/{experiment_id}/
  ├─ result.json    # 工作流状态 & 脚本结果
  └─ stdout.log     # ANSA 标准输出日志
```

## 核心模块

### `app/api/` — API 层

FastAPI 应用初始化，提供 REST 端点（启动/轮询工作流）和 WebSocket 端点（实时 stdout 流推送）。

### `app/agents/` — 智能体节点

`AnsaAgent` 封装了工作流中的 ANSA 操作节点：

- **`validate_inputs`** — 验证模型文件和脚本路径
- **`run_ansa`** — 打开模型并执行脚本
- **`should_run`** — 条件路由（验证通过则执行，否则跳至保存结果）

### `app/graph/` — 工作流

- **`state.py`** — 定义工作流状态（`AnsaAgentState`）：实验 ID、模型路径、脚本路径、执行状态、结果等
- **`workflow.py`** — 构建 LangGraph 工作流图，提供同步/异步执行入口

### `app/core/` — 核心功能

| 模块 | 说明 |
|------|------|
| `ansa_backend.py` | ANSA 进程管理 & IAP 协议通信 |
| `project.py` | 项目 CRUD、模型加载/保存、脚本执行 |
| `checks.py` | 质量检查（网格、几何、穿透、通用） |
| `connections.py` | 连接定义读取与实现 |
| `export.py` | 求解器格式 & 几何格式导出 |
| `mesh.py` | 批量网格划分 |
| `session.py` | 会话状态管理（含撤销/重做） |

### `scripts/` — ANSA 脚本

- **`part_classifier.py`** — 零件分类器：按命名规则识别零件、焊点、螺栓、螺母、垫片等类别，并生成分类 PNG 快照

## 测试

```bash
# 运行全部测试
poetry run pytest

# 运行指定测试文件
poetry run pytest tests/core/test_ansa_backend.py -v
poetry run pytest tests/core/test_project.py -v
```

测试覆盖：

- **`test_ansa_backend.py`** — IAP 协议连接、握手、脚本执行、进程生命周期、参数注入
- **`test_project.py`** — 项目创建/加载/保存、模型打开、结果状态校验、脚本解析

## License

见项目根目录 [LICENSE](../LICENSE) 文件。
