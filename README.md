# 患者智能辅助 Agent 基础后端

本仓库当前实现的是“患者智能辅助 Agent”项目的基础后端，已落地的能力包括：

- 患者基础信息
- 病历记录
- 就诊记录
- 图片上传与 `image_id` 引用
- MCP 风格工具注册与调用
- 基于 LangChain 的单 Agent 编排
- 会话级短期记忆
- 长期记忆第一阶段：抽取、存储、基础召回
- 基于 Qwen Omni 的语音播报与本地 `mp3` 保存
- 面向患者聊天工作台的会话与附件接口

`患者智能辅助Agent_PRD.md` 是上位产品文档，范围明显大于当前代码实现。当前仓库不是完整的多模态医疗平台，也没有正式登录态、权限平台、审计平台或多 Agent 协作能力。

## 技术栈

- Python
- FastAPI
- SQLAlchemy 1.4
- Pydantic 1.x
- SQLite：主业务库
- PostgreSQL：长期记忆库
- LangChain

## 安装与启动

安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

启动服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

常用地址：

- Swagger: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- 健康检查: `http://127.0.0.1:8000/health`

## 核心接口

基础数据：

- `POST /api/v1/patients`
- `GET /api/v1/patients`
- `GET /api/v1/patients/{patient_id}`
- `GET /api/v1/patients/by-patient-no/{patient_no}`
- `PATCH /api/v1/patients/{patient_id}`
- `POST /api/v1/patients/{patient_id}/medical-records`
- `GET /api/v1/patients/{patient_id}/medical-records`
- `GET /api/v1/medical-records/{record_id}`
- `PATCH /api/v1/medical-records/{record_id}`
- `POST /api/v1/patients/{patient_id}/visits`
- `GET /api/v1/patients/{patient_id}/visits`
- `GET /api/v1/visits/{visit_id}`
- `PATCH /api/v1/visits/{visit_id}`

图片：

- `POST /api/v1/images/upload`
- `GET /api/v1/images/{image_id}`

MCP / 工具：

- `GET /api/v1/mcp/servers`
- `GET /api/v1/mcp/tools`
- `POST /api/v1/mcp/tools/{tool_name}/invoke`
- `POST /api/v1/mcp/agent/invoke`
- `POST /api/v1/mcp/case-image/search-query`
- `POST /api/v1/mcp/case-image/analyze`

Agent：

- `POST /api/v1/agent/invoke`
- `POST /api/v1/agent/stream`

聊天工作台：

- `POST /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{session_id}`
- `PATCH /api/v1/chat/sessions/{session_id}`
- `GET /api/v1/chat/sessions/{session_id}/messages`
- `GET /api/v1/chat/sessions/{session_id}/context`
- `POST /api/v1/chat/attachments/upload`
- `GET /api/v1/chat/attachments/{attachment_id}/preview`
- `GET /api/v1/chat/attachments/{attachment_id}/file`
- `DELETE /api/v1/chat/attachments/{attachment_id}`

长期记忆：

- `GET /api/v1/memory/patients/{patient_id}/events`
- `GET /api/v1/memory/patients/{patient_id}/profiles`
- `POST /api/v1/memory/patients/{patient_id}/recall`
- `GET /api/v1/memory/jobs/{job_id}`

语音：

- `POST /api/v1/tts/synthesize`
- `GET /api/v1/tts/files/{file_name}`

## Agent 主链路

当前推荐业务入口是 `POST /api/v1/agent/invoke`。

主链路：

1. `preflight`
   - 患者定位
   - 身份核验
   - 图片上下文装载
   - 会话上下文恢复
   - 长期记忆召回注入
2. `tool_calling`
   - LangChain tool-calling 优先
   - 失败时回退到启发式工具路由
   - 工具调用前统一做参数校验、日期归一化、患者归属校验
3. `postprocess`
   - 生成最终答复
   - `with_audio=true` 时自动生成音频
   - 写回会话消息与执行轨迹

语音不是模型工具循环的一部分，而是系统后处理能力。

## 会话与记忆

### 短期记忆

- 以 `chat_sessions + messages` 持久化
- `POST /api/v1/agent/invoke` 支持可选 `session_id`
- 不传 `session_id` 时自动创建会话
- 默认只恢复最近几轮 `user / assistant` 自然对话
- `tool_call`、`tool_result`、身份核验等消息会持久化，但不会回灌给模型

### 长期记忆

当前已实现：

- `event_memory`
- `profile_memory`
- `memory_extraction_job`
- 抽取后写入 embedding
- 事件召回的 dense / keyword / RRF 融合
- Agent 在 `preflight` 后将长期记忆摘要注入 system prompt

当前仍未完成：

- 更完整的 recall log
- 分布式任务队列
- 更成熟的生产级检索治理

## 常用环境变量

项目启动时会自动加载根目录 `.env`，默认不覆盖已有系统环境变量。可参考 [`.env.example`](/F:/patient_agent/.env.example)。

常用变量：

```env
AGENT_LLM_PROVIDER=qwen
AGENT_LLM_MODEL=qwen-plus
QWEN_API_KEY=your_qwen_api_key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
QWEN_VISION_MODEL=qwen-vl-max-latest
QWEN_OMNI_TTS_MODEL=qwen3-omni-flash
QWEN_OMNI_TTS_VOICE=Cherry

DATABASE_URL=sqlite:///./patient_agent.db
MEMORY_DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/patient_agent_memory
MEMORY_EXTRACTION_ENABLED=true
MEMORY_EXTRACTION_POLL_INTERVAL_SECONDS=5
MEMORY_EXTRACTION_BATCH_SIZE=1
MEMORY_EXTRACTION_MAX_RETRIES=3
MEMORY_EMBEDDING_ENABLED=true
MEMORY_EMBEDDING_MODEL=text-embedding-v4
MEMORY_EMBEDDING_DIMENSIONS=1024
MEMORY_RETRIEVAL_ENABLED=true
MEMORY_RETRIEVAL_TOPK=8
MEMORY_RETRIEVAL_DENSE_TOPN=10
MEMORY_RETRIEVAL_KEYWORD_TOPN=10
MEMORY_RRF_K=60
```

## 当前边界

当前仍未实现：

- 删除基础业务资源的接口
- 正式鉴权 / 授权体系
- 完整审计日志
- 生产级文件清理策略
- 多 Agent 协作

## 测试

全量测试命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

截至 2026-05-27，当前仓库本地全量测试为 37 个用例，覆盖：

- 基础 API
- MCP 工具与身份核验
- Agent tool-calling、流式与会话恢复
- 图片上传与病例图分析
- TTS
- 聊天工作台会话与附件
- 长期记忆抽取、重试、profile 覆盖与召回
