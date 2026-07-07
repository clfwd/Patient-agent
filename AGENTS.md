# AGENTS

## 项目定位

本仓库当前实现的是“患者智能辅助 Agent”项目中的基础后端模块，聚焦以下能力：

- 患者基础信息
- 病历记录
- 就诊记录
- 图片上传与 `image_id` 引用
- MCP 风格工具注册与调用
- 基于工具的单 Agent 编排
- 会话级短期记忆
- 长期记忆第一阶段：抽取、存储、基础召回
- 基于 Qwen Omni 的语音播报
- 患者聊天工作台需要的会话与附件接口

`患者智能辅助Agent_PRD.md` 是上位产品文档，范围明显大于当前实现。后续 Agent 不要把 PRD 中的完整多模态平台、风控系统、正式权限平台等能力误判为“代码已完成”。

## 技术栈

- Python
- FastAPI
- SQLAlchemy 1.4
- Pydantic 1.x
- SQLite：主业务库
- PostgreSQL：长期记忆库
- LangChain
- 前端工作台：React 18 + TypeScript 5 + Vite 5 + Tailwind CSS 3 + `react-router-dom` + `lucide-react`
- 仓库已包含 `components.json` 与 `shadcn/ui` 兼容别名配置
- 当前前端实际落地的 `shared/ui` 组件仍以仓库内自建轻量 primitives 为主，尚未大规模引入官方 `shadcn/ui` 生成组件

## 代码地图

- `app/main.py`
  - `create_app(database_url=None, memory_database_url=None, start_memory_worker=None)` 是应用工厂
  - 初始化主库、长期记忆库、图片存储、MCP registry、TTS service、Agent service
  - 注册全部路由
- `app/db/models.py`
  - 主业务 ORM：`Patient`、`MedicalRecord`、`Visit`、`UploadedImage`、`ChatSession`、`Message`、`ChatAttachment`
- `app/db/repositories.py`
  - 主业务 CRUD
  - `search_records()` 与 `search_visits()` 是泛化查询入口
  - `ChatSessionRepository`、`MessageRepository`、`ChatAttachmentRepository` 负责工作台会话与附件
- `app/memory/`
  - `db.py`：长期记忆数据库初始化
  - `models.py`：`event_memory`、`profile_memory`、`memory_extraction_job`
  - `repositories.py`：长期记忆与 job 仓储
  - `extractor.py`：长期记忆抽取
  - `retrieval.py`：dense / keyword / RRF 召回
  - `service.py`：长期记忆业务规则
  - `worker.py`：单 worker 轮询执行 job
- `app/mcp/router.py`
  - 工具定义、工具注册、敏感工具前置身份核验
- `app/mcp/api.py`
  - MCP FastAPI 接口
- `app/mcp/qwen_client.py`
  - Qwen OpenAI-compatible 客户端与病例图片分析逻辑
- `app/tts/service.py`
  - Qwen Omni 语音生成与本地 `mp3` 落盘
- `app/agent/service.py`
  - 单 Agent 编排核心
  - 当前主链路为 `preflight -> tool_calling -> postprocess`
  - LLM tool-calling 优先，失败时回退到启发式工具路由
  - 会话恢复、消息持久化、长期记忆注入都在这里编排
- `app/agent/tools.py`
  - Agent 工具 wrapper
  - 参数校验、上下文注入、患者归属校验、工具调用轨迹记录
- `app/agent/api.py`
  - `POST /api/v1/agent/invoke`
  - `POST /api/v1/agent/stream`
- `app/agent/schemas.py`
  - Agent 请求响应模型
  - Chat session / message / context 模型
- `app/tool_routing.py`
  - Agent 与 MCP 共用的启发式工具选择逻辑
- `frontend/`
  - 患者端聊天工作台前端工程
  - 使用 Vite 构建
  - `src/app`：页面入口与路由
  - `src/features/chat`：消息流、输入区、工作台 hook
  - `src/features/session`：会话侧栏
  - `src/features/context`：右侧上下文栏
  - `src/features/agent`：执行状态展示
  - `src/shared/api`：前端 API 封装
  - `src/shared/types`：前端类型
  - `src/shared/ui`：轻量 UI primitives
- `tests/test_agent_api.py`
  - Agent tool-calling、患者归属控制、会话恢复测试
- `tests/test_chat_workspace_api.py`
  - 会话与附件接口测试
- `tests/test_memory_api.py`
  - 长期记忆抽取、重试、profile 覆盖测试
- `tests/test_memory_retrieval.py`
  - 长期记忆召回测试

## 当前接口范围

- `GET /health`
- 患者：创建、列表、按 `patient_id` 查询、按 `patient_no` 直查、更新
- 病历：创建、按患者列表、按 `record_id` 查询、更新
- 就诊：创建、按患者列表、按 `visit_id` 查询、更新
- 图片：
  - `POST /api/v1/images/upload`
  - `GET /api/v1/images/{image_id}`
- MCP：
  - `GET /api/v1/mcp/servers`
  - `GET /api/v1/mcp/tools`
  - `POST /api/v1/mcp/tools/{tool_name}/invoke`
  - `POST /api/v1/mcp/agent/invoke`
  - `POST /api/v1/mcp/case-image/search-query`
  - `POST /api/v1/mcp/case-image/analyze`
- Agent：
  - `POST /api/v1/agent/invoke`
  - `POST /api/v1/agent/stream`
- Chat workspace：
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
- Memory：
  - `GET /api/v1/memory/patients/{patient_id}/events`
  - `GET /api/v1/memory/patients/{patient_id}/profiles`
  - `POST /api/v1/memory/patients/{patient_id}/recall`
  - `GET /api/v1/memory/jobs/{job_id}`
- 语音：
  - `POST /api/v1/tts/synthesize`
  - `GET /api/v1/tts/files/{file_name}`

## MCP 工具设计约定

查询类工具按稳定业务能力设计，不按问法膨胀。当前推荐：

- `patient.get_patient_profile`
- `medical_record.search_records`
- `visit.search_visits`
- `image.analyze_uploaded_image`
- `identity.verify_patient_identity`
- `speech.generate_audio_file`

其中 `medical_record.search_records` 和 `visit.search_visits` 统一支持：

- 主体定位字段：`patient_id`、`patient_no`
- 精确定位字段：`record_id` 或 `visit_no`
- 时间约束字段：`date_from`、`date_to`
- 排序字段：`sort_by`、`sort_order`
- 数量字段：`limit`

## MCP 身份核验约定

- `identity.verify_patient_identity` 是显式核验工具
- 以下敏感工具在调用前会自动执行前置身份核验：
  - `patient.*`
  - `medical_record.*`
  - `visit.*`
  - `case_image.*`
  - `image.*`
- 默认至少需要一个核验字段：
  - `verify_name`
  - `verify_phone`
  - `verify_id_card`
- 如果仅通过 `id_card` 定位患者，还必须额外提供姓名或手机号作为第二因子
- 直接 MCP API 调用敏感工具时，仍然是“每次工具调用前核验”
- Agent 内部调用敏感工具时，入口只核验一次，后续只做参数归属校验和患者上下文一致性校验
- 核验失败时返回 `403`
- 患者归属不一致（`patient_context_mismatch`）也返回 `403`
- 当前仅实现“前置身份核验”，还没有正式登录态、令牌体系和审计日志

## Agent 约定

- `POST /api/v1/agent/invoke` 是当前推荐业务入口
- `POST /api/v1/agent/stream` 提供 SSE 流式输出
- `message` 必填
- `session_id` 可选，用于恢复会话上下文
- `patient_id` / `patient_no` / `visit_no` 是可选辅助定位字段
- `image_id` 是旧的单图字段，当前也支持 `attachments`
- `with_audio` 默认 `true`
- Agent 返回结构化执行轨迹，但不暴露完整思维链
- 语音属于后处理能力，不由模型在工具循环中自行决定
- 响应继续兼容 `intent` 字段，但推荐优先依赖 `tool_calls`、`agent_trace`、`final_answer`
- `used_models.tool_calling_mode` 用于区分 `langchain_openai`、`langchain_qwen`、`custom_llm` 与 `heuristic-fallback`

前端工作台约定：

- 默认入口是 `frontend/`
- 本地开发地址默认 `http://127.0.0.1:5173`
- 工作台优先走 `POST /api/v1/agent/stream`
- 当前流式能力是“阶段实时 + 最终答案切块推送”，不是模型 token 级真流式
- 当前已支持：
  - 多轮会话切换
  - 图片附件上传与追问
  - 结构化身份核验字段
  - 音频回复播放器与下载
  - 右侧 Agent 轨迹展示

## 会话与记忆约定

### 短期记忆

- 使用 `chat_sessions` 与 `messages` 持久化
- 默认只恢复最近几轮 `user / assistant` 自然对话
- `tool_call`、`tool_result`、身份核验等执行消息只持久化，不回灌给模型

### 长期记忆

- 使用独立 `MEMORY_DATABASE_URL`
- 当前表结构：
  - `event_memory`
  - `profile_memory`
  - `memory_extraction_job`
- 默认规则：
  - 同一 `session_id` 每累计 5 条 `user_input` 创建一个抽取 job
  - worker 单线程轮询执行
  - 支持重试
- 当前已实现：
  - embedding 入库
  - dense / keyword / RRF 召回
  - Agent `preflight` 后注入长期记忆摘要

## 环境变量

推荐显式配置：

- `AGENT_LLM_PROVIDER`
- `AGENT_LLM_MODEL`
- `AGENT_LLM_API_KEY`
- `AGENT_LLM_BASE_URL`
- `AGENT_GRAPH_ENABLED`
- `AGENT_GRAPH_REQUIRE_LANGGRAPH`

LangGraph 编排相关：

- `AGENT_GRAPH_ENABLED` 默认 `false`，用于后续切换 LangGraph 多节点编排路径；Phase 0 仅完成依赖与兼容开关接入，默认仍走现有单 Agent 链路
- `AGENT_GRAPH_REQUIRE_LANGGRAPH` 默认 `false`，仅在 `AGENT_GRAPH_ENABLED=true` 时生效；设为 `true` 且 `langgraph` 不可导入时，Agent service 初始化应失败并返回 `langgraph_dependency_missing`

长期记忆相关：

- `MEMORY_DATABASE_URL`
- `MEMORY_EXTRACTION_ENABLED`
- `MEMORY_EXTRACTION_POLL_INTERVAL_SECONDS`
- `MEMORY_EXTRACTION_BATCH_SIZE`
- `MEMORY_EXTRACTION_MAX_RETRIES`
- `MEMORY_EMBEDDING_ENABLED`
- `MEMORY_EMBEDDING_MODEL`
- `MEMORY_EMBEDDING_DIMENSIONS`
- `MEMORY_RETRIEVAL_ENABLED`
- `MEMORY_RETRIEVAL_TOPK`
- `MEMORY_RETRIEVAL_DENSE_TOPN`
- `MEMORY_RETRIEVAL_KEYWORD_TOPN`
- `MEMORY_RRF_K`

## 当前未实现

- 删除基础业务资源的接口
- 正式鉴权 / 授权体系
- 完整审计日志
- 生产级文件清理策略
- 多 Agent 协作

## 运行与测试命令

安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

启动服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

启动前端：

```powershell
cd frontend
npm install
npm run dev
```

运行全部测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

截至 2026-05-27，全量测试为 37 个用例。

## 文档地图

- `README.md`：项目入口说明
- `docs/integration-guide.md`：调用方接入文档
- `docs/architecture.md`：研发视角架构说明
- `docs/runbook.md`：运行与排障说明
- `docs/handoff.md`：阶段状态

## 协作提醒

- 当前工作区不是 Git 仓库，无法依赖 `git status` 做变更审计
- 项目已有中文命名与中文文档，后续文档默认保持中文
- 如新增接口或环境变量，至少同步更新 `README.md`、`AGENTS.md` 与 `docs/` 对应页面
