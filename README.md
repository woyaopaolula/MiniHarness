# MiniHarness

MiniHarness 是一个面向代码任务的轻量级 Coding Agent Runtime。它把模型提出的工具调用放入受控执行链路中，统一完成参数校验、工作区限制、工具执行、实时事件记录、MySQL 持久化和自动化评测。

项目目标不是重新训练模型，也不是简单封装某个 Agent 框架，而是实现模型与实际工具之间可控、可追踪、可测试的运行时。

## 当前状态

- Phase 1-8 已完成。
- 支持本地 Mock、OpenAI 兼容 API 和 Ollama 开源模型。
- 已在本地 `qwen2.5-coder:3b` 上跑通真实 Function Calling。
- 使用 MySQL 8.4 保存任务、执行事件和工具调用。
- 提供 FastAPI 异步任务接口和协作取消。
- 使用隐藏 pytest 进行 Coding Agent 自动评测。
- 当前自动化测试：`98 passed`。

## 核心能力

```text
用户任务
  ↓
FastAPI / CLI
  ↓
AgentRuntime
  ↓
ModelAdapter → Mock / OpenAI / Ollama-Qwen
  ↓
ToolExecutor → 参数校验 → 执行策略
  ↓
Read / Search / Write / RunTests
  ↓
实时事件与工具结果 → MySQL
  ↓
隐藏 pytest → 独立任务评分
```

主要机制：

- 统一 `BaseTool`、`ToolRegistry` 和 `ToolExecutor`。
- Pydantic 运行时参数校验。
- 工作区路径隔离和原子文件写入。
- pytest 固定命令、超时终止和输出截断。
- 多轮 Agent Loop、最大迭代次数和工具预算。
- MySQL 任务状态机、实时事件轨迹和有限中断识别。
- FastAPI 后台任务、状态查询和协作取消。
- Mock 与真实模型共用同一套 Runtime。
- 隐藏测试自动评分、JSON/CSV 实验报告和重复实验。

## 技术栈

- Python 3.11
- FastAPI、Uvicorn
- Pydantic 2、pydantic-settings
- SQLAlchemy 2、PyMySQL、MySQL 8.4
- OpenAI Python SDK
- Ollama、Qwen2.5-Coder
- pytest

## 快速开始

以下命令在 Windows Anaconda Prompt 的项目根目录执行。

首次创建环境：

```cmd
conda env create -f environment.yml & conda activate miniharness & python -m pip install -r requirements.txt
```

使用已有环境：

```cmd
conda activate miniharness & python -m pip install -r requirements.txt
```

首次使用需要从示例创建本地配置：

```cmd
copy .env.example .env
```

当前项目默认为本地 Ollama Qwen：

```text
MINIHARNESS_MODEL_PROVIDER=ollama
MINIHARNESS_OLLAMA_MODEL=qwen2.5-coder:3b
MINIHARNESS_OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
```

启动 MySQL 和 Ollama：

```cmd
python scripts\mysql_dev.py start & python scripts\qwen_dev.py start
```

首次下载 Qwen 权重：

```cmd
python scripts\qwen_dev.py pull
```

启动 API：

```cmd
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

访问：

```text
http://127.0.0.1:8000/docs
```

## API

| 方法 | 路径 | 作用 |
|---|---|---|
| `POST` | `/tasks` | 创建任务并返回 `202 + task_id` |
| `GET` | `/tasks/{task_id}` | 查询任务状态与最终结果 |
| `GET` | `/tasks/{task_id}/events` | 查询实时执行事件 |
| `GET` | `/tasks/{task_id}/tool-calls` | 查询工具调用记录 |
| `POST` | `/tasks/{task_id}/cancel` | 请求协作取消 |
| `GET` | `/health` | 检查 API 与 MySQL |

示例：

```json
{
  "prompt": "修复 src/calculator.py 中的 add 函数并运行测试"
}
```

取消是协作式的，会在下一轮模型调用前或下一次工具调用前生效。系统不会强杀正在阻塞的网络请求。

## 命令行运行

不启动 HTTP 服务也可以同步执行一次任务：

```cmd
python scripts\run_agent.py "修复当前项目的测试失败" --workspace D:\path\to\workspace
```

任务、事件和工具调用仍会写入 MySQL。

## 自动化评测

Mock 金标准用于验证评测器：

```cmd
python scripts\run_evaluation.py --mode mock
```

本地 Qwen 评测：

```cmd
python scripts\run_evaluation.py --mode ollama --repetitions 1
```

真实模型 Smoke Test：

```cmd
python scripts\run_evaluation.py --mode ollama --task-id calculator_add --repetitions 1
```

改进测试路径反馈和系统提示后的真实 Qwen 结果：

```text
qwen2.5-coder:3b
3 tasks × 1 trial
hidden-test task success: 3/3 = 100%
agent-completed cases: 2/3
mean tool calls: 4.33
mean elapsed: 345.8 seconds
total tokens: 11659
```

三组真实对照：

| 策略 | 隐藏测试通过 | Agent 正常结束 | 平均耗时 | Token |
|---|---:|---:|---:|---:|
| 原始基线 | 2/3 | 3/3 | 146.3s | 7167 |
| 强制一次自检 | 1/3 | 2/3 | 441.2s | 18147 |
| 改进提示与测试错误反馈 | 3/3 | 2/3 | 345.8s | 11659 |

这是自建 3 任务小样本在 CPU 推理、单次运行条件下的结果，不是通用 Qwen Benchmark。强制自检反而降低 3B 成功率的负结果也被保留。

详细报告：

- [docs/architecture.md](docs/architecture.md)
- [docs/phase-guide.md](docs/phase-guide.md)
- [docs/evaluation.md](docs/evaluation.md)
- [docs/operations.md](docs/operations.md)
- [docs/resume-project.md](docs/resume-project.md)

## 项目结构

```text
app/
├── api/          FastAPI 路由
├── core/         Agent Loop、模型适配、任务编排、后台管理
├── evaluation/   任务加载、隐藏测试评分和指标汇总
├── models/       Agent 消息、工具调用和结果数据契约
├── storage/      SQLAlchemy 模型、MySQL 连接与 Repository
├── tools/        工具接口、注册、执行和工作区工具
├── bootstrap.py  API/CLI 共用的应用组装入口
└── main.py       FastAPI 应用工厂

data/
├── evaluation/   公开任务夹具与隐藏验收测试
├── results/      实际生成的 JSON/CSV 实验报告
├── mysql/        本地 MySQL 数据，Git 忽略
└── ollama/       本地 Ollama 和模型，Git 忽略
```

## 测试

```cmd
python -m pytest tests -v
```

测试包含：

- 工具注册、参数校验与异常边界。
- 文件搜索、写入和路径越界拦截。
- pytest 执行、超时和输出截断。
- Mock 与 OpenAI 协议转换。
- Agent Loop、预算与取消。
- 真实 MySQL 建表、事务、状态机和事件记录。
- FastAPI 后台执行、查询和取消。
- 评测隔离、隐藏测试和防“只声称完成”验证。

## 已知限制

- 当前不是完整操作系统沙箱；pytest 仍会执行工作区代码。
- MySQL 建表使用 `create_all`，尚未接入 Alembic 迁移。
- 后台执行使用进程内线程池，不支持多 API worker 可靠取消。
- 服务重启后会保留数据库记录，但不会自动重放副作用操作。
- Qwen 当前在 CPU 上推理，速度较慢。
- 自定义评测集目前只有 3 个任务、真实 Qwen 只完成 1 次运行。

这些限制应在面试和技术文档中明确说明，不应包装成已完成的分布式调度、完整故障恢复或通用 Benchmark。
