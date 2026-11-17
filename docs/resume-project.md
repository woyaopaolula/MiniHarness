# MiniHarness 简历与面试表述

## 项目定位

不要把它写成“训练了一个代码大模型”或“完整分布式 Agent 平台”。

准确表述：

> 面向代码任务的轻量级 Coding Agent Runtime，重点实现模型工具调用的参数校验、安全执行、状态持久化、可观测性和自动评测。

## 简历项目简介

**MiniHarness：面向代码任务的 Coding Agent 运行时**

技术栈：Python、FastAPI、Pydantic、SQLAlchemy、MySQL、Ollama、OpenAI API、pytest

> 设计并实现面向代码修复任务的 Agent Harness，通过统一工具接口、Pydantic 参数校验和工作区安全控制，将模型 Tool Calling 接入文件检索、原子写入和 pytest 执行；基于 MySQL 状态机、事务和事件表实现任务轨迹持久化，并通过 FastAPI 提供异步任务、状态查询和协作取消；构建隐藏测试驱动的自动评测流程，使用本地 Qwen2.5-Coder 完成真实工具调用和代码修复实验。

## 可展开的项目亮点

1. **模块化工具运行时**：抽象 BaseTool、Registry、Executor 和 Workspace，解耦 Agent Loop 与具体工具实现，统一参数校验、异常分类和耗时记录。
2. **代码执行安全边界**：拒绝越界路径和绝对路径，保护 Git/环境文件，使用原子文件写入；测试执行采用固定命令、超时终止、输出截断和参数注入拦截。
3. **持久化与可观测性**：使用 MySQL 保存任务状态、模型事件和工具调用，通过行锁执行状态转换并记录每一步轨迹。
4. **真实模型与自动评测**：通过 ModelAdapter 支持 Mock、OpenAI 兼容 API 和 Ollama Qwen，使用隐藏 pytest 而非模型自述判断任务成功，输出成功率、工具次数、Token 和耗时报告。

## 可使用的事实数据

```text
自动化测试：97 passed
真实模型：qwen2.5-coder:3b，Ollama Function Calling
自建任务集：3 tasks
真实单次结果：2/3，隐藏测试成功率 66.7%
平均工具调用：2.33
总 Token：7167
```

必须同时注明实验条件，尤其是小样本、CPU 推理、单次运行。不能把 66.7% 说成通用模型成功率。

## 常见追问

### 为什么不用 LangChain？

项目目标是实现并理解 Harness 的核心机制，包括参数校验、工具边界、状态机、事件和评测。直接依赖高层 Agent 框架会隐藏这些关键逻辑。OpenAI SDK 只用于底层模型协议。

### 怎么避免模型乱执行？

模型只生成建议调用；ToolExecutor 负责参数校验，Workspace 限制文件边界，WriteFileTool 保护敏感路径，RunTestsTool 不接受任意命令，Runtime 限制模型轮数和工具预算。

### 怎么做故障恢复？

当前实现是事件持久化和停滞任务识别，把长期无心跳的 `RUNNING` 任务标为 `INTERRUPTED`。没有自动重放写文件和命令，因为副作用操作需要幂等性设计，不能用“重新运行一次”冒充可靠恢复。

### 为什么模型完成了却判失败？

Runtime 的 `completed` 只表示模型返回最终答案。任务成功由隐藏测试决定。真实 Qwen 在 `parse_port` 中声称完成，但没有抛出正确的 `ValueError`，因此被判定失败。

## 不宜写入简历的内容

- “多节点分布式 Agent 调度”
- “完整故障恢复平台”
- “通用 Coding Benchmark 第一”
- 虚构的成功率提升和性能百分比
- 把 Qwen 本地实验写成生产流量结果
- 把工作区路径限制写成完整容器安全沙箱
