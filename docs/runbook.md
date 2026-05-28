# 运行与排障手册

本文档面向本地运行、联调与基础排障场景。

## 1. 运行前提

- 已安装 Python
- 已创建虚拟环境 `.venv`
- 已安装 `requirements.txt` 中依赖
- 若需要长期记忆，已准备 PostgreSQL

安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. 启动服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## 3. 关键环境变量

| 变量 | 常用程度 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | 常用 | 主业务数据库，默认是项目根目录 `patient_agent.db` |
| `AGENT_LLM_PROVIDER` | 常用 | `openai` 或 `qwen` |
| `AGENT_LLM_MODEL` | 常用 | Agent tool-calling 模型 |
| `AGENT_LLM_API_KEY` | 常用 | Agent tool-calling API key |
| `AGENT_LLM_BASE_URL` | 可选 | Agent tool-calling base URL |
| `QWEN_API_KEY` | 图像分析 / 语音常用 | Qwen / DashScope API key |
| `QWEN_BASE_URL` | 可选 | 默认为 DashScope compatible-mode 地址 |
| `QWEN_MODEL` | 可选 | MCP 路由或总结模型 |
| `QWEN_VISION_MODEL` | 图像分析常用 | 图像分析模型 |
| `QWEN_OMNI_TTS_MODEL` | 语音常用 | 语音播报模型 |
| `QWEN_OMNI_TTS_VOICE` | 可选 | 默认音色 |
| `MEMORY_DATABASE_URL` | 长期记忆必需 | 长期记忆数据库连接串 |
| `MEMORY_EXTRACTION_ENABLED` | 常用 | 是否启动长期记忆抽取 worker |
| `MEMORY_EMBEDDING_ENABLED` | 常用 | 是否为事件记忆写 embedding |
| `MEMORY_RETRIEVAL_ENABLED` | 常用 | 是否启用长期记忆召回 |

## 4. 启动后检查

健康检查：

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health | Select-Object -ExpandProperty Content
```

文档地址：

- `http://127.0.0.1:8000/docs`

## 5. 常见排障

### 5.1 `pip install` 失败或代理异常

优先检查：

```powershell
echo $env:HTTP_PROXY
echo $env:HTTPS_PROXY
echo $env:ALL_PROXY
echo $env:PIP_NO_INDEX
```

### 5.2 图像分析或语音提示 API key 未配置

检查：

```powershell
echo $env:QWEN_API_KEY
```

### 5.3 Agent 没有走真实 tool-calling

优先检查：

- `AGENT_LLM_PROVIDER`
- `AGENT_LLM_MODEL`
- `AGENT_LLM_API_KEY`
- `AGENT_LLM_BASE_URL`

如果配置不完整，Agent 会回退到 `heuristic-fallback`。可以从响应里的 `used_models.tool_calling_mode` 判断当前是否真的走了 LangChain。

### 5.4 长期记忆服务不可用

优先检查：

- `MEMORY_DATABASE_URL` 是否可连接
- 启动日志里是否有 `memory_init_error`
- `MEMORY_EXTRACTION_ENABLED` 是否开启
- PostgreSQL 是否具备当前表结构

### 5.5 长期记忆没有被召回

优先检查：

- 是否已经累计到 5 条 `user_input`
- 对应 `memory_extraction_job` 是否已完成
- `MEMORY_RETRIEVAL_ENABLED` 是否为 `true`
- `MEMORY_EMBEDDING_ENABLED` 是否开启

可直接调用：

- `GET /api/v1/memory/patients/{patient_id}/events`
- `GET /api/v1/memory/patients/{patient_id}/profiles`
- `POST /api/v1/memory/patients/{patient_id}/recall`

### 5.6 Agent 返回 `403`

通常表示：

- 身份核验失败
- 患者归属不一致

优先检查：

- `verify_name / verify_phone / verify_id_card`
- `patient_id / patient_no / visit_no / image_id` 是否指向了另一个患者

### 5.7 `agent/stream` 前端没有收到完整事件

优先检查：

- 前端是否按 `text/event-stream` 处理
- 是否正确消费 `session.created`、`answer.delta`、`answer.done`
- 服务端是否提前触发了 `agent.error`

### 5.8 FastAPI 启动时出现 `on_event is deprecated`

截至 2026-05-27，项目仍使用 `@app.on_event("startup")` 与 `@app.on_event("shutdown")`。这会产生 DeprecationWarning，但当前不影响本地运行与测试通过。

## 6. 本地验证命令

运行全部测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

单独运行 Agent 测试：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_agent_api -v
```

单独运行会话工作台测试：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_chat_workspace_api -v
```

单独运行长期记忆测试：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_memory_api tests.test_memory_retrieval -v
```

## 7. 当前运行边界

当前适合：

- 本地开发
- Swagger 联调
- 基础功能演示

暂不包含：

- 生产级鉴权
- 完整审计日志
- 生产级文件生命周期管理
- Docker 化部署

## 8. 已知注意点

- `app.main` 当前仍使用 `@app.on_event("startup")` / `@app.on_event("shutdown")`，运行测试时会看到 DeprecationWarning，但当前不影响功能。
- 源码中仍有部分历史乱码字符串，主要影响 OpenAPI 文案和少量错误提示；如果要对外演示 Swagger，建议后续单独清理一轮中文编码问题。
