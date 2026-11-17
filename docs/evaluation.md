# MiniHarness 自动评测报告

## 1. 评测目标

评测回答一个问题：

> Coding Agent 是否通过真实代码修改和隐藏测试完成了任务？

模型是否说“已完成”不参与判分。

## 2. 方法

每个任务包含：

```text
task.json
workspace/
evaluation_tests/
scripted_plan.json
```

流程：

```text
复制 workspace 到临时目录
→ Agent 只能看到 workspace
→ Agent 完成后复制隐藏测试
→ 固定 pytest 命令执行
→ 通过率、工具次数、Iteration、Token、耗时写入报告
```

成功条件：

```text
test_exit_code == 0
```

## 3. 当前任务

| 任务 | 能力 |
|---|---|
| `calculator_add` | 简单算术 Bug 修复 |
| `normalize_tags` | 字符串分割、空白、大小写和空值 |
| `parse_port` | 整数转换和输入范围异常 |

## 4. 金标准 Mock

命令：

```cmd
python scripts\run_evaluation.py --mode mock
```

结果：

```text
3/3 passed
success rate: 100%
mean tool calls: 3.0
total tokens: 0
```

该结果只证明评测流水线、工具和隐藏测试正确。它不是模型效果，不能作为简历性能数据。

报告：

- `data/results/phase7_mock.json`
- `data/results/phase7_mock.csv`

## 5. 真实 Qwen 实验

环境：

```text
model: qwen2.5-coder:3b
quantization: Q4_K_M
serving: Ollama 0.6.8
provider: Ollama OpenAI-compatible endpoint
execution: CPU inference
temperature: 0
tasks: 3
repetitions: 1
```

命令：

```cmd
python scripts\run_evaluation.py --mode ollama --repetitions 1
```

汇总：

```text
task success rate: 2/3 = 66.7%
mean tool calls: 2.33
mean elapsed: 146.3 seconds
total tokens: 7167
```

| 任务 | 成功 | 工具 | 模型轮次 | 耗时 | Token |
|---|---:|---|---:|---:|---:|
| `calculator_add` | 是 | read, write | 3 | 76.2s | 2007 |
| `normalize_tags` | 是 | read, write, run_tests | 4 | 173.2s | 3018 |
| `parse_port` | 否 | read, write | 3 | 189.5s | 2142 |

报告：

- `data/results/qwen_phase7.json`
- `data/results/qwen_phase7.csv`

## 6. 失败分析

`parse_port` 中，模型没有抛出 `ValueError`，而是打印警告后继续返回端口。Agent 状态为 `completed`，但隐藏测试发现 4 个行为错误：

```text
agent_status: completed
task_success: false
failure_stage: tests
```

这说明 Runtime 完成和任务业务成功必须分开评价。

`normalize_tags` 中，模型一度选择不存在的测试文件，工具返回结构化错误，但代码本身正确，隐藏测试最终通过。

## 7. 有效性边界

- 只有 3 个简单任务。
- 真实 Qwen 只运行 1 次。
- 当前是 CPU 推理，耗时不代表 GPU 性能。
- 任务由单人设计，可能包含与 prompt 风格相关的偏差。
- 隐藏测试在 Agent 完成后注入，但测试进程仍与工作区共享运行时。
- 66.7% 仅适用于上述实验条件。

## 8. 后续实验

建议扩展：

1. 增加 10～20 个不同难度任务。
2. 每任务重复 3～5 次，报告均值、方差和失败分布。
3. 比较 3B 与 7B/14B 模型。
4. 对比是否启用工具错误反馈。
5. 对比不同迭代和工具预算。
6. 比较 CPU 与 CUDA 推理延迟。
7. 增加上下文长度与 Token 消耗实验。
