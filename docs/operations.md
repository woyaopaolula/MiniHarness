# 本地运行与故障排查

## CI

GitHub Actions 工作流位于 `.github/workflows/ci.yml`。每次 push 到 `main` 时：

1. 启动 MySQL 8.4 service container。
2. 安装 `requirements.txt`。
3. 运行全部 pytest。
4. 运行 Mock 评测。
5. 上传 JSON/CSV 评测 artifact。

CI 使用临时环境变量，不读取本地 `.env`。

## 服务

启动 MySQL：

```cmd
python scripts\mysql_dev.py start
```

启动 Ollama：

```cmd
python scripts\qwen_dev.py start
```

检查状态：

```cmd
python scripts\mysql_dev.py status & python scripts\qwen_dev.py status
```

停止服务：

```cmd
python scripts\mysql_dev.py stop & python scripts\qwen_dev.py stop
```

## 模型

当前默认：

```text
qwen2.5-coder:3b
```

下载模型：

```cmd
python scripts\qwen_dev.py pull
```

指定其他 Ollama 模型：

```cmd
python scripts\qwen_dev.py pull --model qwen2.5-coder:7b
```

然后修改 `.env` 中的 `MINIHARNESS_OLLAMA_MODEL`。

## 配置

| 环境变量 | 作用 |
|---|---|
| `MINIHARNESS_DB_HOST` | MySQL 主机 |
| `MINIHARNESS_DB_PORT` | MySQL 端口 |
| `MINIHARNESS_DB_USER` | 应用数据库用户 |
| `MINIHARNESS_DB_PASSWORD` | 应用数据库密码 |
| `MINIHARNESS_DB_NAME` | 开发数据库名 |
| `MINIHARNESS_MODEL_PROVIDER` | `ollama` 或 `openai` |
| `MINIHARNESS_OLLAMA_MODEL` | Ollama 模型名 |
| `MINIHARNESS_OLLAMA_BASE_URL` | Ollama OpenAI 兼容地址 |
| `MINIHARNESS_LLM_MODEL` | 远程 OpenAI 兼容模型名 |
| `MINIHARNESS_LLM_API_KEY` | 远程模型密钥 |
| `MINIHARNESS_LLM_BASE_URL` | 远程兼容接口 |
| `MINIHARNESS_WORKSPACE_ROOT` | Agent 允许操作的根目录 |

`.env` 被 Git 忽略。仓库只提交 `.env.example`。

## 常见问题

### MySQL 无法启动

```cmd
python scripts\mysql_dev.py status
```

查看 `logs/mysql-error.log`。不要删除 `data/mysql`；其中包含本地任务数据。

### Ollama API 无法连接

```cmd
python scripts\qwen_dev.py status
python scripts\qwen_dev.py start
```

查看 `logs/ollama-stderr.log`。

### 模型响应非常慢

当前 Conda 构建虽然检测到 GPU，但实际仍可能回退 CPU。日志出现：

```text
CPU model buffer size
```

说明本轮是 CPU 推理。可以改用官方 CUDA Ollama 或 llama.cpp CUDA runner。

### API 启动提示模型未配置

检查 `.env`：

```text
MINIHARNESS_MODEL_PROVIDER=ollama
MINIHARNESS_OLLAMA_MODEL=qwen2.5-coder:3b
```

或者切换为 `openai` 并配置远程模型。

### tests/test_api.py 有 testclient 弃用警告

这是 FastAPI/Starlette 测试客户端对未来 `httpx2` 的依赖提示。当前测试行为正常，不影响 API。
