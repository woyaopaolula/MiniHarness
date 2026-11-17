# 从 Phase 0 到 Phase 8：项目学习路线

## Phase 0：工程基础

问题：项目需要一个稳定的本地开发环境。

完成内容：

- Python 3.11 Conda 环境。
- Git 版本管理。
- 目录、依赖清单和忽略规则。
- MySQL、Ollama 本地运行基础。

## Phase 1：工具接口与注册表

问题：主循环不应该为每个工具写一组 `if/elif`。

完成内容：

- `BaseTool` 统一工具契约。
- `ToolRegistry` 注册、校验和查询。
- `ReadFileTool` 第一个真实工具。

关键代码：

- `app/tools/base.py`
- `app/tools/registry.py`
- `app/tools/file_tools.py`

## Phase 2：参数校验与统一执行

问题：模型生成的 JSON 是不可信输入。

完成内容：

- 每个工具声明 Pydantic 参数模型。
- `ToolExecutor` 查找、校验、执行和计时。
- 统一成功、参数错误、业务错误和内部错误结构。

关键代码：

- `app/tools/executor.py`
- `app/tools/file_tools.py`

## Phase 3：代码工作区工具

问题：Agent 需要实际搜索、修改和验证代码。

完成内容：

- 工作区统一路径边界。
- 字面文本搜索和结果限制。
- 原子文件写入。
- pytest 固定命令、超时、进程树终止和输出截断。

关键代码：

- `app/tools/workspace.py`
- `app/tools/file_tools.py`
- `app/tools/test_tools.py`

## Phase 4：Agent Loop 与模型适配

问题：工具可以执行，但没有模型驱动循环。

完成内容：

- `ModelAdapter` 统一模型接口。
- Mock 和 OpenAI 兼容适配器。
- 多轮模型与工具循环。
- 迭代预算、工具预算、Token 和工具轨迹。

关键代码：

- `app/core/model.py`
- `app/core/runtime.py`
- `app/models/agent.py`

## Phase 5：MySQL 持久化

问题：程序退出后内存中的任务和轨迹会丢失。

完成内容：

- MySQL 8.4 本地服务和配置。
- SQLAlchemy 连接池和短事务。
- Task、Event、ToolCall 三张表。
- 原子状态转换和事件心跳。
- 实时 Repository Event Sink。
- 停滞后标记 `INTERRUPTED` 的基础。

关键代码：

- `app/storage/`
- `app/core/task_service.py`

## Phase 6：FastAPI 后台接口

问题：任务需要作为服务提交和查询。

完成内容：

- `POST /tasks` 创建后台任务。
- 状态、事件、工具记录查询。
- 线程池 TaskManager。
- 协作取消和 `CANCELLED` 状态。
- 单进程 API 生命周期管理。

关键代码：

- `app/api/`
- `app/core/task_manager.py`
- `app/main.py`

## Phase 7：自动评测与真实 Qwen

问题：模型声称完成不代表代码正确。

完成内容：

- 任务夹具、公开测试和隐藏测试。
- 隔离临时工作区。
- 真实 pytest 判分。
- 成功率、工具次数、迭代、Token 和耗时。
- 重复实验 JSON/CSV 报告。
- Ollama Qwen2.5-Coder 3B 真实 Function Calling。
- Qwen 三任务真实实验。
- 测试路径错误反馈和可选的写后自检策略。
- 原始基线、强制自检和错误反馈改进的三组对照。

关键代码：

- `app/evaluation/`
- `data/evaluation/tasks/`
- `scripts/run_evaluation.py`
- `scripts/qwen_dev.py`

## Phase 8：交付与文档

问题：系统需要能让别人复现、运行和面试讲解。

完成内容：

- 根 README。
- 架构、运行、学习和实验文档。
- API/CLI 共用 bootstrap。
- 同步 CLI 任务入口。
- 真实能力与限制的简历表述。

## 面试理解检查

你应该能回答：

1. 为什么需要 ToolExecutor，而不是 Runtime 直接调用函数？
2. Pydantic 参数校验和工具内部路径校验分别解决什么？
3. 为什么 pytest 失败不等于工具 infrastructure failure？
4. MySQL 状态转换为什么需要行锁？
5. `completed` 为什么不等于任务成功？
6. 事件持久化为什么不等于完整故障恢复？
7. 为什么评测要用隐藏测试，而不能相信模型回答？
8. Ollama 模式和 OpenAI 模式为什么不需要修改 Runtime？

如果这些问题能用自己的语言回答，项目才真正属于你。
