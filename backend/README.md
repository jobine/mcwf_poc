# MCWF PoC — Backend

MCWF（MetaCreate Workflow）概念验证后端，将 **ANSA**（FEA 前处理工具）与基于 **LangGraph** 的智能体工作流系统集成。通过 IAP（Inter-ANSA Protocol）协议与 ANSA 进程通信，并以 **FastAPI REST + WebSocket** 接口实时推送工作流执行状态。

## 目录

- [项目结构](#项目结构)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [环境变量](#环境变量)
- [Agent 配置（graph.json）](#agent-配置graphjson)
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
│   └── config.py       # 集中配置（Pydantic Settings，从 .env 读取）
├── scripts/            # ANSA Python 脚本（零件分类等）
├── tests/              # 单元测试
├── data/
│   └── shared/         # 共享模型文件（demo.ansa）
├── experiments/        # 运行时实验输出
├── graph.json          # Agent 配置（名称、脚本、参数）
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

复制 `.env.example` 为 `.env` 并根据实际环境修改路径：

```bash
cp .env.example .env
```

`.env` 文件示例：

```ini
# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key_here
LANGCHAIN_PROJECT=mcwf_poc

# Server
HOST=0.0.0.0
PORT=8000

# Directory Configuration (所有路径配置必须在此指定)
EXPERIMENTS_DIR=experiments
SCRIPTS_DIR=scripts
DATA_SHARED_DIR=data/shared
GRAPH_CONFIG_PATH=graph.json
```

> **注意**：`EXPERIMENTS_DIR`、`SCRIPTS_DIR`、`DATA_SHARED_DIR`、`GRAPH_CONFIG_PATH` 均为必填项，没有硬编码的默认值。

### 启动服务

```bash
poetry run uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

服务启动后：

- Swagger UI：`http://localhost:8000/docs`
- REST 端点：`GET /workflow`、`POST /experiment`、`POST /experiment/stream`、`GET /experiment/{id}`
- WebSocket 端点：`ws://localhost:8000/experiment/{id}/stream`

### 独立运行工作流

```bash
poetry run python -m app.graph.workflow
```

## 环境变量

所有目录配置通过 `.env` 文件提供，无硬编码默认值。

| 变量 | 必填 | 说明 |
|------|------|------|
| `EXPERIMENTS_DIR` | ✅ | 实验输出目录 |
| `SCRIPTS_DIR` | ✅ | ANSA 脚本目录 |
| `DATA_SHARED_DIR` | ✅ | 共享模型数据目录 |
| `GRAPH_CONFIG_PATH` | ✅ | Agent 配置文件路径（`graph.json`） |
| `HOST` | — | 服务监听地址（默认 `0.0.0.0`） |
| `PORT` | — | 服务监听端口（默认 `8000`） |
| `LANGCHAIN_TRACING_V2` | — | 启用 LangSmith 追踪 |
| `LANGCHAIN_API_KEY` | — | LangSmith API 密钥 |
| `LANGCHAIN_PROJECT` | — | LangSmith 项目名称 |
| `ANSA_HOME` | — | ANSA 安装路径 |

## Agent 配置（graph.json）

Agent 的运行时配置存放在 `graph.json` 中，工作流启动时按 `name` 查找对应 Agent 条目。

```json
{
  "agents": [
    {
      "name": "classifier",
      "type": "AnsaAgent",
      "model_path": "demo.ansa",
      "script_path": "part_classifier.py",
      "script_kwargs": {}
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `name` | Agent 逻辑名称，同时作为工作流中的图节点名称（例如 `classifier`） |
| `type` | Agent 类型（当前仅支持 `AnsaAgent`） |
| `model_path` | 模型文件名，运行时与 `DATA_SHARED_DIR` 拼接为完整路径 |
| `script_path` | 脚本文件名，运行时与 `SCRIPTS_DIR` 拼接为完整路径 |
| `script_kwargs` | 传递给脚本执行的额外关键字参数（JSON 对象） |

每个 Agent 实例对应工作流中的一个节点，节点名称即 Agent 的 `name`。Agent 的 `execute()` 方法内部完成输入验证和 ANSA 执行，并通过 `on_event` 回调发出事件。

## API 接口

采用 REST + WebSocket 两阶段架构：先通过 HTTP 启动工作流，再通过 WebSocket 实时接收事件流。

### `GET /workflow`

获取编译后的 ANSA 工作流图的 JSON 表示（节点、边及其关系）。

- **响应 200**：工作流图 JSON（包含 `nodes`、`edges` 等结构信息）

### `POST /experiment`

启动 ANSA 工作流（后台异步执行），立即返回 `experiment_id`。无事件流。

- **响应 202**：`{"experiment_id": "<uuid>"}`

### `POST /experiment/stream`

启动 ANSA 工作流并开启事件流。返回 `experiment_id` 后，可通过 WebSocket 接收实时事件。

- **响应 202**：`{"experiment_id": "<uuid>"}`

### `GET /experiment/{experiment_id}`

轮询工作流最终结果。

- **响应 200**：工作流完成，返回最终状态 JSON
- **响应 202**：工作流仍在运行，`{"status": "running"}`
- **响应 404**：未知的 `experiment_id`

### `WS /experiment/{experiment_id}/stream`

实时流式推送工作流事件（含 15 秒心跳保活）。需先通过 `POST /experiment/stream` 启动工作流。

**服务端 → 客户端消息**（JSON 格式，含 `type` 字段）：

| 事件类型 | 字段 | 说明 |
|---------|------|------|
| `workflow_started` | `experiment_id` | 工作流已初始化 |
| `agent_started` | `agent` | Agent 节点开始执行 |
| `stdout` | `data` | ANSA 实时输出行 |
| `agent_completed` | `agent`, `status` | Agent 节点执行完成（`success` / `error`） |
| `workflow_completed` | `experiment_id`, `status`, `result`, `error` | 工作流完成，含最终状态 |
| `error` | `data` | 不可恢复的异常信息 |
| `heartbeat` | `data` | 心跳保活（空字符串） |

**客户端 → 服务端消息**（预留，暂未实现）：

| 动作 | 说明 |
|------|------|
| `cancel` | 请求优雅取消 |
| `input` | Human-in-the-loop 回复 |

**客户端示例（JavaScript）：**

```javascript
// 1. 启动带事件流的工作流
const resp = await fetch("/experiment/stream", { method: "POST" });
const { experiment_id } = await resp.json();

// 2. 连接事件流
const ws = new WebSocket(`ws://host/experiment/${experiment_id}/stream`);
ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    switch (msg.type) {
        case "workflow_started":  console.log("Started:", msg.experiment_id); break;
        case "agent_started":     console.log("Agent started:", msg.agent); break;
        case "stdout":            console.log(msg.data); break;
        case "agent_completed":   console.log("Agent done:", msg.agent, msg.status); break;
        case "workflow_completed": console.log("Done:", msg); ws.close(); break;
        case "error":             console.error(msg.data); ws.close(); break;
    }
};
```

## 架构概览

```
┌──────────────────────────────────────────────────┐
│           FastAPI Server (:8000)                  │
│  POST /experiment          → 启动工作流（无事件流）│
│  POST /experiment/stream   → 启动工作流（有事件流）│
│  GET  /workflow            → 获取工作流图 JSON     │
│  GET  /experiment/{id}     → 轮询结果              │
│  WS   /experiment/{id}/stream → 实时事件流         │
└──────────────────┬───────────────────────────────┘
                   ↓
┌──────────────────────────────────────────────────┐
│       LangGraph Workflow (graph/)                │
│  graph.json → Agent 配置（name, paths, kwargs）   │
│  .env       → 目录配置（data, scripts, ...）      │
│                                                  │
│  START → init_experiment                         │
│       → classifier (validate + run, retry×3)     │
│       → deinit_workflow → END                    │
└──────────────────┬───────────────────────────────┘
                   ↓
┌──────────────────────────────────────────────────┐
│       ANSA Backend (core/ansa_backend.py)        │
│  AnsaProcess                                     │
│  ├─ IAP Connection (TCP Socket)                  │
│  ├─ Stdout Reader (异步线程)                      │
│  └─ Script Execution (参数注入)                   │
└──────────────────┬───────────────────────────────┘
                   ↓
┌──────────────────────────────────────────────────┐
│          ANSA (FEA Pre-processor)                │
│  模型加载 · 脚本执行 · 网格操作 · 导出             │
└──────────────────────────────────────────────────┘

输出: experiments/{experiment_id}/
  ├─ result.json    # 工作流状态 & 脚本结果
  ├─ stdout.log     # ANSA 标准输出日志
  └─ events.jsonl   # 事件流记录（仅 stream 模式）
```

### 工作流节点说明

工作流由三个顺序执行的节点组成：

| 节点 | 函数 | 说明 |
|------|------|------|
| `init_experiment` | `workflow.init_experiment()` | 创建实验目录，发出 `workflow_started` 事件 |
| `classifier` | `AnsaAgent.execute()` | 验证输入 → 启动 ANSA → 执行脚本（retry×3），发出 `agent_started`/`stdout`/`agent_completed` 事件 |
| `deinit_workflow` | `workflow.deinit_experiment()` | 写入 `result.json` 和 `stdout.log`，发出 `workflow_completed` 事件 |

### 请求时序图

下图展示了一次完整的实验请求流程——从客户端发起 `POST /experiment/stream` 到通过 WebSocket 实时接收事件并获取最终结果：

```mermaid
sequenceDiagram
    participant B as Browser
    participant F as FastAPI
    participant T as ThreadPool
    participant W as LangGraph Workflow
    participant A as ANSA Process

    B->>F: POST /experiment/stream
    F->>F: 生成 experiment_id<br/>创建 event_q<br/>注册 _experiments
    F->>T: run_in_executor(_run_workflow_with_events)
    F-->>B: 202 {"experiment_id": "..."}

    B->>F: WS /experiment/{id}/stream
    F-->>B: WebSocket 连接建立

    T->>W: workflow.invoke(state)
    W->>W: init_experiment<br/>创建实验目录
    Note over W: → workflow_started 事件

    W->>W: classifier (validate inputs)
    Note over W: → agent_started 事件

    W->>A: 启动 ANSA 进程<br/>加载模型 & 执行脚本

    loop ANSA 实时输出
        A-->>W: stdout line
        W-->>T: on_stdout(line)
        T-->>F: event_q.put(stdout event)
        F-->>B: {"type":"stdout","data":"<line>"}
    end

    loop 空闲保活 (每 15s)
        F-->>B: {"type":"heartbeat","data":""}
    end

    A-->>W: 脚本执行完成
    Note over W: → agent_completed 事件

    W->>W: deinit_workflow<br/>写入 result.json & stdout.log
    Note over W: → workflow_completed 事件
    W-->>T: 返回 final_state
    T-->>F: 存储 final_state<br/>event_q.put(None)
    F-->>B: 发送剩余事件后关闭
    B->>F: 关闭 WebSocket

    opt 轮询结果
        B->>F: GET /experiment/{id}
        F-->>B: 200 {status, result, …}
    end
```

## 核心模块

### `app/api/` — API 层

FastAPI 应用初始化，提供 REST 端点（启动/轮询工作流）和 WebSocket 端点（实时事件流推送）。

### `app/agents/` — 智能体节点

`AnsaAgent` 封装了工作流中的 ANSA 操作节点，每个 Agent 实例对应一个图节点：

- **`execute()`** — 单一入口方法：验证输入（模型/脚本路径） → 启动 ANSA 进程 → 执行脚本 → 返回结果。配置 `RetryPolicy`（最多重试 3 次）。内部通过 `on_event` 回调发出 `agent_started`、`stdout`、`agent_completed` 事件。

### `app/graph/` — 工作流

- **`state.py`** — 定义工作流状态（`AnsaAgentState`）：实验 ID、模型路径、脚本路径、执行状态、结果等
- **`workflow.py`** — 构建 LangGraph 顺序工作流图（`init_experiment → classifier → deinit_workflow`），Agent 节点配备重试策略，提供同步/异步执行入口及 JSON 图导出。`init_experiment` 和 `deinit_experiment` 为带事件回调的节点工厂函数。

### `app/core/` — 核心功能

| 模块 | 说明 |
|------|------|
| `ansa_backend.py` | ANSA 进程管理 & IAP 协议通信（stdout 采用 UTF-8/cp1252 自适应解码） |
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
cd backend
poetry run pytest tests/ -v

# 运行指定测试文件
poetry run pytest tests/core/test_ansa_backend.py -v
poetry run pytest tests/core/test_project.py -v
```

测试覆盖：

- **`test_ansa_backend.py`** — IAP 协议连接、握手、脚本执行、进程生命周期、参数注入
- **`test_project.py`** — 项目创建/加载/保存、模型打开、结果状态校验、脚本解析

## License

见项目根目录 [LICENSE](../LICENSE) 文件。
