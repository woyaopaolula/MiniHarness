# MiniHarness 架构

## 1. 设计原则

MiniHarness 把模型和工具执行分开：

- 模型只提出行动建议。
- Harness 决定是否允许执行。
- 工具只处理已经过校验的参数。
- Runtime 保存每一步的真实结果。
- 评测器根据隐藏测试判断任务是否成功。

核心约束是：模型输出视为不可信外部输入，不能直接执行。

## 2. 分层结构

```text
API / CLI
    ↓
TaskService
    ↓
AgentRuntime
    ├── ModelAdapter
    │     ├── MockModelAdapter
    │     ├── OpenAICompatibleModelAdapter
    │     └── OllamaModelAdapter
    └── ToolExecutor
          ↓
       ToolRegistry
          ├── ReadFileTool
          ├── SearchFilesTool
          ├── WriteFileTool
          └── RunTestsTool

TaskService → TaskRepository → SQLAlchemy → MySQL
AgentRuntime → AgentEventListener → TaskRepository
```

## 3. 模块职责

| 模块 | 职责 |
|---|---|
| `api` | HTTP 参数与响应、状态码、后台任务触发 |
| `core.runtime` | 多轮模型与工具循环、预算、取消、事件 |
| `core.model` | 屏蔽 Mock、OpenAI 和 Ollama 的接口差异 |
| `core.task_service` | 创建任务、启动执行、保存最终结果 |
| `core.task_manager` | 进程内线程池和取消事件 |
| `models` | 消息、工具调用、运行结果等 Pydantic 契约 |
| `storage` | MySQL 连接、表结构、事务和 Repository |
| `tools` | 工具抽象、注册、校验、工作区安全与执行 |
| `evaluation` | 隔离工作区、隐藏测试、指标和报告 |
| `bootstrap` | API/CLI 共用的模型、工具、数据库组装 |

## 4. 工具执行链路

模型返回 Tool Call：

```json
{
  "name": "read_file",
  "arguments": {"path": "src/app.py"}
}
```

Harness 执行：

```text
1. Registry 根据名称查找工具
2. Pydantic 校验参数
3. ToolExecutor 捕获异常并计时
4. 工具解析工作区路径
5. 工具执行具体业务
6. 返回 ToolExecutionResult
7. 结果作为 tool 消息反馈模型
```

`success=True` 表示工具执行成功。对 `run_tests` 而言，`data.passed=False` 表示 pytest 正常运行但测试失败，这是模型需要继续修复的业务结果。

## 5. 工作区安全

所有文件工具共用 `Workspace.resolve_path()`：

- 拒绝绝对路径。
- 拒绝盘符路径。
- 拒绝 `..` 越界。
- 解析符号链接后再次检查边界。
- 写文件拒绝 `.git`、`.codex`、`.agents` 和 `.env`。
- 写入使用同目录临时文件加原子替换。

`RunTestsTool` 不接受任意 Shell 命令，只执行：

```text
python -m pytest <workspace-relative path>
```

同时设置超时、进程树终止和输出截断。该机制防止模型误调用，但不是完整恶意代码沙箱。

## 6. Agent Runtime

每轮：

```text
检查取消
→ 调用模型
→ 检查取消
→ 如果有 Tool Call，执行工具
→ 把统一结果反馈模型
→ 继续
```

终止状态：

- `completed`：模型返回最终回答。
- `failed`：模型异常或空响应。
- `cancelled`：取消检查点生效。
- `iteration_limit`：模型轮数耗尽。
- `tool_call_limit`：工具预算耗尽。

`completed` 只表示 Runtime 正常结束，不代表代码正确。

可选 `verification_rounds` 会在写文件后模型准备结束时追加一次验证提示。由于真实 3B 消融实验中该策略降低了成功率，当前默认值为 0，只作为可配置实验策略。

## 7. MySQL 状态模型

```text
PENDING → RUNNING → COMPLETED
                  ├→ FAILED
                  ├→ CANCELLED
                  └→ INTERRUPTED
```

表：

- `tasks`：任务状态、答案、Token、耗时。
- `task_events`：`run_started`、`model_response`、工具开始/结束、`run_finished`。
- `tool_calls`：工具参数、结果、错误和耗时。

状态转换使用 `SELECT ... FOR UPDATE` 行锁。事件写入同时更新任务心跳。

`recover_stale_running_tasks()` 可以把长时间无心跳的 `RUNNING` 任务标为 `INTERRUPTED`，但不会自动重放可能产生副作用的操作。

## 8. 后台 API 与取消

`POST /tasks` 先写 `PENDING` 并返回，后台线程再执行。查询接口始终读取 MySQL。

取消使用独立 `threading.Event`：

- 模型调用前检查。
- 模型响应后检查。
- 每次工具调用前检查。

若模型或工具正在阻塞，必须等其返回后才能到达检查点。因此这是协作取消，不是强制中断。

## 9. 自动评测

```text
复制任务 workspace 到临时目录
→ 运行 Agent
→ Agent 结束后注入隐藏测试
→ pytest 独立判分
→ 保存成功率、工具次数、Token、耗时
```

成功条件：

```text
hidden_tests_passed == True
```

模型最终文本不能改变判分。

## 10. 设计边界

当前未实现：

- Alembic 数据库迁移。
- 多进程任务调度与分布式锁。
- 操作系统级容器沙箱。
- 安全重放和完整故障恢复。
- 上下文摘要与 Token 预算裁剪。
- 大规模、多难度 Coding Benchmark。
