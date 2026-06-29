# 架构说明

本文档描述当前仓库中前后端一体的代码结构、请求链路与 Agent 编排方式。

## 1. 当前架构范围

当前仓库实现的是“患者智能辅助 Agent”的一体化基础工程，不是完整平台。当前已落地内容包括：

- 后端基础业务模块
  - 患者基础信息
  - 病历记录
  - 就诊记录
  - 图片上传与 `image_id`
- Agent 与工具编排
  - MCP 工具注册与调用
  - 基于工具的单 Agent 编排
  - 会话级短期记忆
  - 长期记忆第一阶段：抽取、存储、基础召回
  - 基于 Qwen Omni 的语音播报
- 前端患者聊天工作台
  - 三栏工作台布局
  - 多轮会话切换
  - 图片附件上传与追问
  - SSE 状态流与回答流
  - 音频回复展示与下载

说明：

- 当前目标形态是“患者端 AI Agent 工作台”
- 不是传统 Admin 系统
- 不是完整多 Agent 平台
- 也还没有正式登录态、权限平台和审计平台

## 2. 技术栈

后端：

- Python
- FastAPI
- SQLAlchemy 1.4
- Pydantic 1.x
- SQLite：主业务库
- PostgreSQL：长期记忆库
- LangChain

前端：

- React 18
- TypeScript 5
- Vite 5
- Tailwind CSS 3
- `react-router-dom`
- `lucide-react`

关于 `shadcn/ui`：

- 仓库中已包含 [frontend/components.json](/F:/patient_agent/frontend/components.json)
- 当前别名与目录组织兼容 `shadcn/ui`
- 但 [frontend/src/shared/ui](/F:/patient_agent/frontend/src/shared/ui) 中实际落地的仍主要是仓库内自建轻量 primitives
- 尚未大规模引入官方 `shadcn/ui` 生成组件

## 3. 模块分层

### 3.1 后端接口层

- [app/main.py](/F:/patient_agent/app/main.py)
  - 创建 FastAPI 应用
  - 初始化主库与长期记忆库
  - 注册基础路由、MCP 路由、Agent 路由、聊天工作台路由、记忆路由、TTS 路由
- [app/agent/api.py](/F:/patient_agent/app/agent/api.py)
  - `POST /api/v1/agent/invoke`
  - `POST /api/v1/agent/stream`
- [app/mcp/api.py](/F:/patient_agent/app/mcp/api.py)
  - MCP 接口
- [app/tts/api.py](/F:/patient_agent/app/tts/api.py)
  - 音频接口

### 3.2 后端主业务数据层

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

### 3.3 后端 Agent / 工具层

- [app/agent/service.py](/F:/patient_agent/app/agent/service.py)
  - `preflight -> tool_calling -> postprocess`
  - 会话恢复、消息持久化、长期记忆注入
- [app/agent/tools.py](/F:/patient_agent/app/agent/tools.py)
  - 工具参数校验
  - 工具上下文注入
  - 患者归属校验
- [app/mcp/router.py](/F:/patient_agent/app/mcp/router.py)
  - MCP 工具注册
  - 敏感工具前置身份核验
- [app/tool_routing.py](/F:/patient_agent/app/tool_routing.py)
  - 启发式工具路由

### 3.4 后端长期记忆层

- [app/memory/db.py](/F:/patient_agent/app/memory/db.py)
  - 长期记忆数据库初始化
- [app/memory/models.py](/F:/patient_agent/app/memory/models.py)
  - `event_memory`
  - `profile_memory`
  - `memory_extraction_job`
- [app/memory/repositories.py](/F:/patient_agent/app/memory/repositories.py)
  - 记忆与 job 仓储
- [app/memory/retrieval.py](/F:/patient_agent/app/memory/retrieval.py)
  - dense / keyword / RRF 召回
- [app/memory/worker.py](/F:/patient_agent/app/memory/worker.py)
  - 单 worker 轮询执行

### 3.5 前端页面与状态层

- [frontend/src/app/router.tsx](/F:/patient_agent/frontend/src/app/router.tsx)
  - 工作台路由入口
- [frontend/src/app/workspace-page.tsx](/F:/patient_agent/frontend/src/app/workspace-page.tsx)
  - 三栏布局容器
- [frontend/src/features/session/components/session-sidebar.tsx](/F:/patient_agent/frontend/src/features/session/components/session-sidebar.tsx)
  - 左侧会话栏
- [frontend/src/features/chat/components/conversation-view.tsx](/F:/patient_agent/frontend/src/features/chat/components/conversation-view.tsx)
  - 中间聊天区
- [frontend/src/features/chat/components/composer.tsx](/F:/patient_agent/frontend/src/features/chat/components/composer.tsx)
  - 输入区
  - 身份核验区
  - 图片上传入口
- [frontend/src/features/chat/components/message-list.tsx](/F:/patient_agent/frontend/src/features/chat/components/message-list.tsx)
  - 消息列表
  - 图片与音频回复渲染
- [frontend/src/features/context/components/context-sidebar.tsx](/F:/patient_agent/frontend/src/features/context/components/context-sidebar.tsx)
  - 右侧患者摘要、会话状态、Agent 轨迹
- [frontend/src/features/chat/hooks/use-agent-workspace.ts](/F:/patient_agent/frontend/src/features/chat/hooks/use-agent-workspace.ts)
  - 工作台核心状态流
- [frontend/src/shared/api](/F:/patient_agent/frontend/src/shared/api)
  - 前端 API 封装
- [frontend/src/shared/types](/F:/patient_agent/frontend/src/shared/types)
  - 前端类型定义

## 4. 数据结构

主业务库核心表：

- `patients`
- `medical_records`
- `visits`
- `uploaded_images`
- `chat_sessions`
- `messages`
- `chat_attachments`

长期记忆库核心表：

- `event_memory`
- `profile_memory`
- `memory_extraction_job`

关系说明：

- 一个患者可关联多条病历、多次就诊、多张上传图片
- 一个聊天会话可关联多条消息
- 一个聊天会话可关联多条聊天附件
- 聊天附件可引用 `uploaded_images`
- 长期记忆按患者维度组织，但由会话消息触发抽取

## 5. 一次请求的执行链路

### 5.1 普通同步调用

前端通过 `POST /api/v1/agent/invoke` 发起请求，请求体通常包含：

- `message`
- `session_id`
- `verify_name`
- `verify_phone`
- `verify_id_card`
- `attachments`
- `with_audio`

后端主链路：

1. 解析请求并恢复或创建会话
2. 解析本轮附件，得到实际 `image_id`
3. 进入 `preflight`
   - 身份核验
   - 图片上下文装载
   - 长期记忆召回
4. 持久化本轮用户消息
5. 进入 `tool_calling`
   - LLM tool-calling 优先
   - 失败时回退启发式工具路由
6. 进入 `postprocess`
   - 组装最终回答
   - 可选生成音频
7. 持久化最终回答并返回前端

### 5.2 SSE 流式调用

前端通过 `POST /api/v1/agent/stream` 发起请求。

当前流式机制是“按请求连接推送”，不是“按 `session_id` 创建全局 emitter”：

1. `app/agent/api.py` 为当前请求创建独立 `Queue`
2. 定义 `publish(event_name, data)` 回调
3. 后台线程执行 `agent_service.invoke(..., event_callback=publish)`
4. `StreamingResponse` 从队列中持续取事件并写回前端

当前事件类型：

- `session.created`
- `agent.phase`
- `answer.delta`
- `answer.done`
- `audio.ready`
- `agent.error`

说明：

- `session.created` 与 `agent.phase` 由服务层执行过程中通过 `event_callback` 推送
- `answer.done` 为本轮最终结果
- 当前 `answer.delta` 仍是“先得到完整回答，再切块返回”的伪流式，不是 token 级真流式

## 6. 前端状态流

前端工作台状态可分为四层：

- 布局状态
  - 左右侧栏开合
  - 各面板独立滚动
- 会话导航状态
  - 会话列表
  - 当前激活会话
- 会话内容状态
  - 消息数组
  - 附件
  - 当前输入草稿
- 运行时状态
  - `idle -> submitting -> streaming -> success | error`

发送一条消息时，前端行为为：

1. 如有本地图片，先上传附件
2. 乐观插入用户消息
3. 发起 `agent/stream`
4. 收到 `session.created` 后回填路由
5. 收到 `agent.phase` 后更新状态条与轨迹栏
6. 收到 `answer.delta` 后持续拼接助手回复
7. 收到 `answer.done` 后收口最终消息
8. 如有 `audio.ready`，在消息下方展示音频播放器

## 7. 图片链路

图片相关链路不是“前端直接把图片发给大模型”，而是两段式：

1. 前端先把文件上传到后端
2. Agent 需要看图时，后端再根据 `image_id` 从本地读取文件并转成模型可消费的格式

具体过程：

1. 前端调用 `POST /api/v1/chat/attachments/upload`
2. 后端保存文件，并写入：
   - `uploaded_images`
   - `chat_attachments`
3. 前端发送聊天请求时，仅传附件引用或 `image_id`
4. Agent 工具层根据 `image_id` 找到本地文件
5. 图片分析工具把图片文件转成 base64 data URL
6. 再把文本 prompt 与图片内容一并发给视觉模型

当前图片继承规则：

- 本轮显式带了图片，则使用本轮图片
- 本轮没带图，但问题明确提到“这张图”“这个报告”“检查报告”等指代时，才自动沿用本会话最近图片
- 与图片无关的后续追问，不会默认强制绑定上一张图

## 8. 记忆链路

短期记忆：

- 使用 `chat_sessions` 与 `messages`
- 默认只恢复自然对话消息
- 工具执行细节不回灌给模型

长期记忆：

- 每累计一定数量的 `user_input`，创建抽取 job
- worker 轮询执行抽取
- 抽取后的结构化事实进入长期记忆库
- Agent 在 `preflight` 后注入长期记忆摘要

## 9. 当前边界

当前尚未实现或尚未达到生产级的部分包括：

- 正式登录态与授权体系
- 完整审计日志
- 生产级文件清理策略
- 多 Agent 协作
- token 级真流式回答
- 全量官方 `shadcn/ui` 组件体系

因此，当前更准确的定位是：

- 一套可运行的患者端 AI Agent 基础工程
- 含前后端联动工作台
- 含会话、附件、身份核验、音频回复、长期记忆与图片分析链路
- 但仍处于可迭代的工程化阶段
