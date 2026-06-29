# Design: LangGraph Multi-Agent 医疗助手

## Phase 2 细化设计

Medical Knowledge Agent 最小闭环的表结构、检索策略、Graph 接入和测试 fixture 设计见 `phase-2-medical-knowledge.md`。本文件保留总体架构说明，Phase 2 的实现细节以后优先更新该专题文档，避免重复维护。

## Phase 3 Task Board 设计

Phase 3 将 graph 路径从线性 Router 升级为 `task_board` 驱动的有界工作流：

```text
graph_preflight
  -> graph_planner
  -> graph_dispatcher
  -> graph_memory_agent / graph_patient_data_agent / graph_image_analysis_agent / graph_medical_knowledge_agent
  -> graph_join
  -> graph_gap_checker
     -> graph_dispatcher 或 graph_composer
  -> graph_postprocess
  -> END
```

当前实现先采用串行 task board 语义：Dispatcher 每次选择一个 ready task；worker 只产出 `task_results`、`worker_events` 和 `evidence_items`；Join 统一更新任务状态；Gap Checker 负责预算、去重和是否继续调度。该结构后续可切换为 LangGraph `Send` 并行派发，而不改变 worker 输出协议。

## Design Goals

- 在不破坏现有 Agent API 的前提下引入 LangGraph。
- 将“编排控制”和“业务工具能力”分离，避免继续扩大 `PatientAgentService` 的单文件复杂度。
- 多 Agent 节点必须可追踪、可回退、可测试。
- 医疗知识检索必须提供来源，不能成为无依据医学建议生成器。
- 医疗安全校验作为统一出口前的必要节点，而不是散落在各个 Agent 中。

## Overview

建议新增 `app/agent/graph/` 作为 LangGraph 编排层：

- `state.py`：定义图状态。
- `nodes.py`：实现各节点函数。
- `router.py`：实现 Supervisor 路由策略。
- `graph.py`：构建 LangGraph workflow。
- `knowledge.py`：封装医疗知识检索服务调用。
- `safety.py`：封装风险规则与回答降级逻辑。

`PatientAgentService.invoke()` 保持对外入口不变，内部根据配置选择：

1. LangGraph 路径。
2. 现有 LangChain tool-calling 路径。
3. 现有启发式 fallback 路径。

初始阶段可以使用环境变量控制：

- `AGENT_GRAPH_ENABLED`
- `AGENT_GRAPH_REQUIRE_LANGGRAPH`
- `MEDICAL_KNOWLEDGE_RETRIEVAL_ENABLED`

## Modules

### Identity / Preflight

职责：

- 恢复或创建 chat session。
- 解析 `image_id` 与 `attachments`。
- 执行身份核验。
- 召回会话上下文。
- 初始化 `run_id`、trace、工具调用记录。

复用：

- `ChatSessionRecorder`
- 现有附件解析逻辑
- 现有身份核验逻辑

### Supervisor / Router

职责：

- 根据用户问题和请求字段决定需要哪些节点。
- 输出结构化计划，不直接执行业务工具。

路由信号：

- 是否包含患者定位字段。
- 是否包含症状、病历、就诊、检查、药物、图片等关键词。
- 是否包含附件。
- 是否是通用医学知识问题。
- 是否存在高风险关键词。

第一阶段建议采用“规则优先 + LLM 可选”的路由方式，降低对模型稳定性的依赖。

### Patient Data Agent

职责：

- 读取患者基础信息、病历记录、就诊记录。
- 统一输出患者事实摘要。

复用工具：

- `patient.get_patient_profile`
- `medical_record.search_records`
- `visit.search_visits`

约束：

- 只能在身份核验通过后执行。
- 必须遵守患者归属一致性校验。

### Medical Knowledge Agent

职责：

- 基于用户问题和患者事实摘要检索本地医疗知识。
- 返回知识片段、来源、标题、更新时间、排序分数。
- 不直接生成最终患者回答。

建议新增模块：

- `app/knowledge/models.py`
- `app/knowledge/repositories.py`
- `app/knowledge/retrieval.py`
- `app/knowledge/service.py`
- `app/knowledge/api.py` 可后置。

最小表结构：

- `medical_knowledge_document`
  - `id`
  - `title`
  - `source`
  - `source_type`
  - `content`
  - `metadata`
  - `created_at`
  - `updated_at`
- `medical_knowledge_chunk`
  - `id`
  - `document_id`
  - `chunk_index`
  - `content`
  - `embedding`
  - `metadata`
  - `created_at`

第一阶段可以只做 chunk 表和关键词检索；如果复用现有 embedding/RRF 代码成本低，再加入向量召回。

### Image Analysis Agent

职责：

- 判断本轮是否需要分析图片或报告。
- 调用现有图片分析工具。
- 输出结构化发现和不确定性。

复用：

- 当前附件解析逻辑。
- `image.analyze_uploaded_image`。

### Memory Agent

职责：

- 调用长期记忆召回。
- 输出与当前问题相关的长期事件和画像摘要。

复用：

- `app/memory/service.py`
- `app/memory/retrieval.py`

### Evidence / Safety Agent

职责：

- 检查最终回答素材是否有依据。
- 识别高风险医疗场景。
- 给 `Answer Composer` 输出回答约束。

建议第一阶段采用规则为主：

- 急症关键词：胸痛、呼吸困难、意识障碍、严重过敏、大出血、剧烈头痛、抽搐等。
- 高风险建议：自行停药、调整处方剂量、确诊疾病、延误就医。
- 证据不足：没有患者事实、没有知识来源、图片分析失败却生成确定结论。

### Answer Composer Agent

职责：

- 汇总患者事实、医学知识、图片分析、长期记忆和 Safety 约束。
- 输出面向患者的最终回答。
- 保持简明、谨慎、可追溯。

回答结构建议：

- 先回答用户问题。
- 再说明“结合你的记录”。
- 再说明“通用医学知识提示”。
- 如有风险，给出就医或复诊建议。
- 如使用知识库，列出简短来源。

### Postprocess

职责：

- 持久化用户消息、工具消息和最终回答。
- 可选生成音频。
- 创建长期记忆抽取 job。
- 组装现有 `AgentInvokeResponse`。

## Core Flow

1. `PatientAgentService.invoke()` 创建 graph state。
2. `graph_preflight` 执行身份核验、附件、患者上下文和会话恢复。
3. `graph_planner` 生成 `task_board`，并记录高风险规则命中到 `risk_flags`。
4. `graph_dispatcher` 选择 ready task，并路由到对应 worker。
5. worker 只写 `task_results`、`worker_events`、`evidence_items`，不直接改最终任务状态。
6. `graph_join` 根据 `worker_events` 统一更新 `task_board`。
7. `graph_gap_checker` 在预算内决定继续调度或进入 `graph_composer`。
8. `graph_composer` 基于证据和兼容 tool-calling 结果生成 `final_answer`。
9. `graph_postprocess` 生成音频、持久化、返回响应。

## Data / Storage Design

第一阶段新增医疗知识库数据模型时，应尽量独立于患者业务库：

- 如果知识库数据量小，可先放主业务 SQLite，降低运行门槛。
- 如果需要 embedding，可考虑复用长期记忆 PostgreSQL 配置，但不要与患者长期记忆表混用。
- 每条知识召回结果必须带 `document_id`、`title`、`source` 和 `chunk_id`。

Graph state 建议字段：

- `request`
- `session_id`
- `run_id`
- `patient_context`
- `attachments`
- `identity_verification`
- `task_board`
- `current_task`
- `task_results`
- `worker_events`
- `proposed_tasks`
- `evidence_items`
- `risk_flags`
- `join_summary`
- `dispatch_round`
- `patient_facts`
- `knowledge_hits`
- `image_findings`
- `memory_hits`
- `safety_result`
- `final_answer`
- `tool_calls`
- `agent_trace`
- `errors`

## API / Interface Design

对外 API 第一阶段不变：

- `POST /api/v1/agent/invoke`
- `POST /api/v1/agent/stream`

可兼容扩展：

- `AgentTraceSchema.stage` 使用 LangGraph 节点名。
- `AgentTraceSchema.detail` 展示节点摘要。
- `used_models` 增加 `graph_mode`、`router_mode`、`knowledge_retrieval_mode`。

后续可选新增知识库管理接口：

- `POST /api/v1/knowledge/documents`
- `GET /api/v1/knowledge/documents`
- `POST /api/v1/knowledge/search`

这些接口不应阻塞第一阶段 Agent 内部闭环。

## Error Handling

- 身份核验失败：沿用当前 `ServiceError` 与 `403` 映射。
- LangGraph import 失败：当 `AGENT_GRAPH_REQUIRE_LANGGRAPH=false` 时回退旧路径。
- 单个非关键节点失败：记录 trace，继续进入 Safety 和 Composer，但回答必须说明缺失信息。
- 患者数据节点失败：若问题依赖患者数据，返回可恢复错误或要求稍后重试。
- 知识库无结果：不阻断回答，但不得输出来源。
- Safety 命中高风险：不阻断回答，但约束 Composer 输出就医提醒。

## Concurrency, Transactions, Idempotency

- 单次 Agent 调用仍以一个 `run_id` 追踪。
- 消息持久化应集中在 Postprocess，避免多个节点重复写入。
- 工具调用记录可以先存在 state 中，结束时统一持久化。
- SSE 事件由节点开始和结束时发布，事件顺序必须与 graph 执行顺序一致。
- 第一阶段不要求跨请求恢复 graph 中间态。

## Risks And Tradeoffs

- 引入 LangGraph 会增加依赖和状态管理复杂度，因此必须保留旧路径回退。
- 医疗知识库质量直接影响回答质量，第一阶段应强调来源透明，而不是覆盖面。
- 如果 Router 过度依赖 LLM，测试会不稳定；因此规则路由应作为默认基线。
- 如果每个能力都拆成完整 Agent，初期会过度工程化；建议先做节点化，再逐步 Agent 化。
- Safety 规则过严会降低可用性，过松会带来医疗风险；第一阶段宁可保守。

## Verification Plan

- 单元测试覆盖 Router 对典型问题的节点计划。
- 单元测试覆盖 Medical Knowledge Agent 有结果、无结果和来源返回。
- API 测试覆盖 LangGraph enabled 与 disabled 两种路径。
- API 测试覆盖身份失败、患者归属不一致、附件错误的兼容语义。
- SSE 测试覆盖新增阶段事件。
- 手动验证至少三类场景：
  - 通用医学知识问题。
  - 结合患者病历的问题。
  - 高风险症状问题。
## Phase 3.1 Send 并行调度设计

Phase 3.1 将 Phase 3 的串行 task board 调度升级为 LangGraph `Send` 并行派发：

```text
graph_preflight
  -> graph_planner
  -> graph_dispatcher
      -> Send(graph_memory_agent)
      -> Send(graph_patient_data_agent)
      -> Send(graph_image_analysis_agent)
      -> Send(graph_medical_knowledge_agent)
  -> graph_join
  -> graph_gap_checker
      -> graph_dispatcher 或 graph_composer
  -> graph_postprocess
```

核心约束：

- `graph_dispatcher` 一次选出多个 ready task，并按 `priority desc, task_id asc` 稳定排序。
- `max_parallel_tasks` 默认值为 `4`，限制单轮派发宽度。
- 每个 `Send` 分支携带自己的 `current_task`，worker 不再依赖全局唯一任务。
- worker 只返回增量 patch：`task_results`、`worker_events`、`evidence_items`、`tool_calls`、`agent_trace`。
- `AgentState` 对并行写入字段增加 reducer：list 字段前缀感知合并，`plan` 去重合并，`task_results` 字典合并。
- `graph_join` 仍是唯一更新 `task_board` 状态的节点。
- `graph_composer` 在已有 worker 输出时不再调用旧 tool-calling loop，避免图片等工具在 worker 和 composer 中重复执行。

测试边界：

- SQLite 内存库使用 `StaticPool`，不适合作为真实并发 DB 压力测试环境；并行 `Send` 语义通过 router / node 单元测试验证。
- Agent API 测试继续覆盖 graph enabled / disabled、身份失败、患者数据、图片分析、医学知识、风险提示等业务闭环。
## Phase 3.2 Bounded Plan-Execute-Replan

Phase 3.2 upgrades the task-board graph into a bounded Plan-Execute-Replan design with controlled ReAct workers:

```text
graph_preflight
  -> PlannerAgent(graph_planner)
  -> graph_dispatcher
      -> PatientDataAgent / MedicalKnowledgeAgent / image worker / memory worker
  -> graph_join
  -> ReplannerAgent(graph_gap_checker)
      -> graph_dispatcher or ComposerAgent(graph_composer)
  -> graph_postprocess
```

Node roles are intentionally separated:

- Workflow nodes: `graph_preflight`, `graph_dispatcher`, `graph_join`, `graph_postprocess`.
- Reasoning agents: PlannerAgent, ReplannerAgent, ComposerAgent.
- Controlled ReAct worker agents: PatientDataAgent and MedicalKnowledgeAgent.
- Single-shot workers: image analysis and memory retrieval.

PlannerAgent returns structured task intent only. It does not grant tool permission. Effective tools are computed server-side:

```text
effective_allowed_tools =
  planner_allowed_tools
  intersect capability_registry[agent].allowed_tools
  intersect runtime_policy.allowed_tools
```

The same server-side policy caps tool steps:

```text
effective_max_tool_steps = min(task.max_tool_steps, agent_cap.max_tool_steps_cap)
```

PatientDataAgent is a bounded ReAct worker over patient data tools only: `patient.get_patient_profile`, `visit.search_visits`, and `medical_record.search_records`. It may perform multi-step evidence gathering, but it cannot diagnose, interpret images, call knowledge/memory tools, or choose arbitrary patient identifiers. Patient scope remains enforced by `AgentToolExecutor`.

MedicalKnowledgeAgent is a bounded Agentic RAG worker with a deliberately small tool surface: `medical_knowledge.search` and `medical_knowledge.deep_retrieve`. `deep_retrieve` internally handles query rewrite, multi-query retrieval, RRF ranking, lightweight reranking, and evidence compression. These internal RAG steps are not exposed as separate LLM tools.

ReplannerAgent is implemented on the existing `graph_gap_checker` node name for compatibility. It distinguishes `finish`, `continue`, and `force_finish`, where `force_finish` means Composer must produce a degraded answer because budget or recovery limits were reached.

Evidence uses a normalized schema with `patient_specific` and `medical_knowledge` flags so Composer can distinguish patient facts, image findings, general medical knowledge, and historical memory. Safety signals include `safety_level`, `urgent_flags`, `answer_constraints`, and `forbidden_claims`. Phase 3.2 does not add a standalone SafetyAgent, but urgent patterns such as chest pain plus breathing difficulty constrain Composer output.
