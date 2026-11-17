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

## 5. 真实 Qwen 实验环境

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

基础命令：

```cmd
python scripts\run_evaluation.py --mode ollama --repetitions 1
```

## 6. 三组对照

第一次原始基线：

```text
task success rate: 2/3 = 66.7%
mean tool calls: 2.33
mean elapsed: 146.3 seconds
total tokens: 7167
```

强制一次写后自检：

```text
task success rate: 1/3 = 33.3%
mean tool calls: 5.0
mean elapsed: 441.2 seconds
total tokens: 18147
```

自检触发后，3B 在 `calculator_add` 中重复写文件并引入循环导入，在 `normalize_tags` 中未完成修复；只有 `parse_port` 通过。这说明额外自我反思轮次不必然提升小模型可靠性。

改进测试路径错误反馈和系统提示后，重新运行无强制自检基线：

```text
task success rate: 3/3 = 100%
agent completed: 2/3
mean tool calls: 4.33
mean elapsed: 345.8 seconds
total tokens: 11659
```

| 任务 | 隐藏测试 | Agent 完成 | 工具 | 轮次 | 耗时 | Token |
|---|---:|---:|---|---:|---:|---:|
| `calculator_add` | 是 | 是 | search, run_tests, read, write, run_tests | 4 | 381.8s | 3674 |
| `normalize_tags` | 是 | 否 | read, read, write | 4 | 108.3s | 2912 |
| `parse_port` | 是 | 是 | read, write, run_tests, write, run_tests | 5 | 547.1s | 5073 |

`normalize_tags` 的代码已正确修复并通过对隐藏测试，但模型最终返回空响应。因此：

- 功能任务成功率按隐藏测试统计为 3/3。
- 严格 Agent 正常结束率为 2/3。

两份指标必须同时报告，不能用 3/3 掩盖一次空响应。

报告：

- `data/results/qwen_phase7.json`：原始基线
- `data/results/qwen_phase7_verification.json`：强制自检
- `data/results/qwen_phase7_baseline_v2.json`：改进反馈后的最新基线

## 7. 失败分析

`parse_port` 中，模型没有抛出 `ValueError`，而是打印警告后继续返回端口。Agent 状态为 `completed`，但隐藏测试发现 4 个行为错误：

```text
agent_status: completed
task_success: false
failure_stage: tests
```

这说明 Runtime 完成和任务业务成功必须分开评价。

`normalize_tags` 中，模型一度选择不存在的测试文件，工具返回结构化错误，但代码本身正确，隐藏测试最终通过。

## 8. 有效性边界

- 只有 3 个简单任务。
- 真实 Qwen 只运行 1 次。
- 当前是 CPU 推理，耗时不代表 GPU 性能。
- 任务由单人设计，可能包含与 prompt 风格相关的偏差。
- 隐藏测试在 Agent 完成后注入，但测试进程仍与工作区共享运行时。
- 66.7% 仅适用于上述实验条件。

## 9. 后续实验

建议扩展：

1. 增加 10～20 个不同难度任务。
2. 每任务重复 3～5 次，报告均值、方差和失败分布。
3. 比较 3B 与 7B/14B 模型。
4. 对比是否启用工具错误反馈。
5. 对比不同迭代和工具预算。
6. 比较 CPU 与 CUDA 推理延迟。
7. 增加上下文长度与 Token 消耗实验。
