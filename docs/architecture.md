# 架构说明

本文档描述当前后端模块的代码结构、请求链路与 Agent 编排方式。

## 1. 当前架构范围

当前仓库实现的是“患者智能辅助 Agent”的基础后端，不是完整平台。已落地能力包括：

- 患者基础信息
- 病历记录
- 就诊记录
- 图片上传与 `image_id`
- MCP 工具注册与调用
- 基于工具的单 Agent 编排
- 会话级短期记忆
- 长期记忆第一阶段：抽取、存储、基础召回
- 基于 Qwen Omni 的语音播报
- 患者聊天工作台需要的会话与附件接口

## 2. 模块分层

接口层：

- [app/main.py](/F:/patient_agent/app/main.py)
  - 创建 FastAPI 应用
  - 初始化主库与长期记忆库
  - 注册基础路由、MCP 路由、Agent 路由、聊天工作台路由、记忆路由、TTS 路由

主业务数据层：

- [app/db/models.py](/F:/patient_agent/app/db/models.py)
  - `Patient`
  - `MedicalRecord`
  - `Visit`
  - `UploadedImage`
  - `ChatSession`
  - `Message`
  - `ChatAttachment`
- [app/db/repositories.py](/F:/patient_agent/app/db/repositories.py)
  - 基础 CRUD
  - 泛化查询
  - 会话、消息、附件持久化

长期记忆层：

- [app/memory/db.py](/F:/patient_agent/app/memory/db.py)
- [app/memory/models.py](/F:/patient_agent/app/memory/models.py)
- [app/memory/repositories.py](/F:/patient_agent/app/memory/repositories.py)
- [app/memory/extractor.py](/F:/patient_agent/app/memory/extractor.py)
- [app/memory/retrieval.py](/F:/patient_agent/app/memory/retrieval.py)
- [app/memory/service.py](/F:/patient_agent/app/memory/service.py)
- [app/memory/worker.py](/F:/patient_agent/app/memory/worker.py)

MCP / 工具层：

- [app/mcp/router.py](/F:/patient_agent/app/mcp/router.py)
- [app/mcp/api.py](/F:/patient_agent/app/mcp/api.py)
- [app/mcp/qwen_client.py](/F:/patient_agent/app/mcp/qwen_client.py)

Agent 层：

- [app/agent/service.py](/F:/patient_agent/app/agent/service.py)
- [app/agent/tools.py](/F:/patient_agent/app/agent/tools.py)
- [app/agent/state.py](/F:/patient_agent/app/agent/state.py)
- [app/agent/api.py](/F:/patient_agent/app/agent/api.py)
- [app/tool_routing.py](/F:/patient_agent/app/tool_routing.py)

## 3. 数据库结构

### 3.1 主业务库：SQLite

当前主业务库承载：

- `patients`
- `medical_records`
- `visits`
- `uploaded_images`
- `chat_sessions`
- `messages`
- `chat_attachments`

### 3.2 长期记忆库：PostgreSQL

当前长期记忆库承载：

- `event_memory`
- `profile_memory`
- `memory_extraction_job`

这么拆分的原因：

- 不强行把主业务库一次性迁移到 PostgreSQL
- 让长期记忆可以独立演进到 embedding / pgvector / hybrid retrieval
- 保持主业务链路与记忆链路解耦

## 4. Agent 链路

`POST /api/v1/agent/invoke` 与 `POST /api/v1/agent/stream` 共用同一套核心编排。

### 4.1 preflight

职责：

- 患者定位
- 身份核验
- 单图 `image_id` 或附件关联图片装载
- 恢复短期会话上下文
- 查询长期记忆摘要

关键产物：

- `verified_patient`
- `allowed_patient_id`
- `image_context`
- `session_id`
- `long_term_profile_memories`
- `long_term_event_memories`

### 4.2 tool_calling

职责：

- LangChain tool-calling 优先
- 失败时回退到启发式工具路由
- 统一做工具参数校验、日期归一化、患者归属校验

统一处理点：

- schema 校验
- 日期归一化
- `patient_id` / `patient_no` 一致性校验
- `record_id` / `visit_no` / `image_id` 的患者归属校验
- 非法参数拦截

启发式工具选择逻辑统一收口在 [app/tool_routing.py](/F:/patient_agent/app/tool_routing.py)，Agent 与 MCP 共用，避免分叉。

### 4.3 postprocess

职责：

- 生成最终答复
- 整理 `tool_calls`、`steps`、`agent_trace`
- 在 `with_audio=true` 时自动调用 `speech.generate_audio_file`
- 将用户输入、核验、工具调用、最终答复等消息写回 `messages`

## 5. 短期记忆

短期记忆使用 `chat_sessions + messages`。

规则：

- 自动创建会话或复用已有 `session_id`
- 仅 `visible_in_context=true` 的 `user / assistant` 消息参与恢复
- `tool_call`、`tool_result`、身份核验等执行消息只持久化，不回灌给模型
- 前端通过 `GET /api/v1/chat/sessions/{session_id}/context` 读取会话摘要、附件和最近运行状态

## 6. 长期记忆

### 6.1 抽取触发

- 同一 `session_id` 每累计 5 条 `user_input` 自动创建一个 `memory_extraction_job`

### 6.2 抽取结果

写入两类结构：

- `event_memory`
- `profile_memory`

### 6.3 执行模型

- `MemoryExtractionWorker` 单 worker 轮询
- 原子抢占 `pending` job
- 支持失败重试

### 6.4 召回能力

当前已经具备：

- embedding 入库
- dense search
- keyword search
- RRF 融合
- `POST /api/v1/memory/patients/{patient_id}/recall`

Agent 在 `preflight` 后会把长期记忆摘要注入 tool-calling prompt。

## 7. 错误处理

当前错误处理使用结构化错误码：

- Agent 内部通过 `AgentExecutionError`
- 工具参数和权限校验通过 `AgentToolValidationError`
- MCP 结果通过统一映射转成 HTTP 状态码

重点语义：

- 身份核验失败：`403`
- 患者归属不一致：`403`
- 参数错误：`400`
- 资源不存在：`404`
- 下游工具执行失败：`502`

## 8. 当前边界

当前仍未实现：

- 正式鉴权 / 授权体系
- 完整审计日志
- 生产级文件治理策略
- 多 Agent 协作
