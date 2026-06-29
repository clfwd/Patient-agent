# Tasks: LangGraph Multi-Agent 医疗助手

## Phase 0: 依赖与兼容开关

- [x] LG-001 新增 LangGraph 依赖与配置开关
  - Files: `requirements.txt`, `app/agent/service.py`
  - Acceptance: 默认不开启 LangGraph 时，现有 Agent 行为和测试保持不变。

- [x] LG-002 为 graph 模式增加运行配置
  - Files: `app/agent/service.py`, `docs/runbook.md`, `README.md`, `AGENTS.md`
  - Acceptance: 文档说明 `AGENT_GRAPH_ENABLED`、`AGENT_GRAPH_REQUIRE_LANGGRAPH` 等配置含义。

## Phase 1: Graph 编排骨架

- [x] LG-101 新增 `app/agent/graph/` 模块
  - Files: `app/agent/graph/state.py`, `app/agent/graph/nodes.py`, `app/agent/graph/router.py`, `app/agent/graph/graph.py`
  - Acceptance: 可以构建最小 graph，并执行 preflight、router、composer、postprocess 节点。

- [x] LG-102 将现有 preflight 逻辑迁移为可复用节点
  - Files: `app/agent/service.py`, `app/agent/graph/nodes.py`
  - Acceptance: 身份核验、附件解析、会话恢复和长期记忆入口语义不变。

- [x] LG-103 保留旧路径 fallback
  - Files: `app/agent/service.py`
  - Acceptance: LangGraph 不可用或关闭时，仍使用现有 tool-calling / heuristic fallback。

- [x] LG-104 扩展 trace 阶段名称
  - Files: `app/agent/schemas.py`, `app/agent/service.py`, `frontend/src/shared/types`
  - Acceptance: 前端能展示 LangGraph 节点 trace，不破坏旧 trace。

## Phase 2: Medical Knowledge Agent 最小闭环

- [x] LG-201 新增医疗知识数据模型和仓储
  - Files: `app/knowledge/models.py`, `app/knowledge/repositories.py`, `app/knowledge/db.py`
  - Acceptance: 可以写入文档和 chunk，并按关键词检索 chunk。

- [x] LG-202 新增知识检索服务
  - Files: `app/knowledge/retrieval.py`, `app/knowledge/service.py`
  - Acceptance: 输入问题后返回 `content`、`title`、`source`、`document_id`、`chunk_id`。

- [x] LG-203 接入 Medical Knowledge Agent 节点
  - Files: `app/agent/graph/nodes.py`, `app/agent/graph/state.py`
  - Acceptance: 通用医学知识问题能触发知识检索，最终回答包含来源摘要。

- [x] LG-204 添加最小种子知识或测试 fixture
  - Files: `tests/fixtures`, `tests/test_medical_knowledge.py`
  - Acceptance: 测试不依赖外部网络或真实医学数据库。

## Phase 3: Supervisor 与多节点执行

- [x] LG-301 实现规则优先 Router
  - Files: `app/agent/graph/router.py`, `app/tool_routing.py`
  - Acceptance: 患者数据、医学知识、图片、长期记忆、高风险场景能被稳定路由。

- [x] LG-302 接入 Patient Data Agent 节点
  - Files: `app/agent/graph/nodes.py`, `app/agent/tools.py`
  - Acceptance: 结合患者资料的问题会调用现有患者、病历、就诊工具。

- [x] LG-303 接入 Image Analysis Agent 节点
  - Files: `app/agent/graph/nodes.py`
  - Acceptance: 有图片附件且问题引用图片时，会调用现有图片分析工具。

- [x] LG-304 接入 Memory Agent 节点
  - Files: `app/agent/graph/nodes.py`, `app/memory/service.py`
  - Acceptance: 长期记忆启用时，相关记忆进入 graph state 并可被 Composer 使用。

## Phase 4: Safety 与回答组合

- [ ] LG-401 新增 Safety 规则模块
  - Files: `app/agent/graph/safety.py`
  - Acceptance: 高风险症状和高风险建议能被规则命中。

- [ ] LG-402 接入 Evidence / Safety 节点
  - Files: `app/agent/graph/nodes.py`, `app/agent/graph/state.py`
  - Acceptance: Safety 结果能约束最终回答。

- [ ] LG-403 重构 Answer Composer
  - Files: `app/agent/graph/nodes.py`, `app/agent/service.py`
  - Acceptance: 最终回答区分患者事实、医学知识、图片发现和安全提醒。

## Phase 5: 流式事件、测试与文档

- [ ] LG-501 更新 SSE 阶段事件
  - Files: `app/agent/api.py`, `app/agent/service.py`, `frontend/src/features/agent`
  - Acceptance: 前端右侧轨迹能看到 LangGraph 节点阶段。

- [ ] LG-502 补充后端测试
  - Files: `tests/test_agent_api.py`, `tests/test_langgraph_agent.py`, `tests/test_medical_knowledge.py`
  - Acceptance: 覆盖 graph enabled、graph disabled、知识检索、安全降级和身份失败。

- [ ] LG-503 更新项目文档
  - Files: `README.md`, `AGENTS.md`, `docs/architecture.md`, `docs/integration-guide.md`, `docs/runbook.md`, `docs/handoff.md`
  - Acceptance: 新增接口、配置、架构和运行方式与实现一致。

## Verification

- [x] 运行全部后端测试：`.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
- [ ] 若改动前端类型或轨迹展示，运行前端构建：`cd frontend` 后 `npm run build`
- [ ] 手动调用 `/api/v1/agent/invoke` 验证通用医学知识问题。
- [ ] 手动调用 `/api/v1/agent/invoke` 验证结合患者资料的问题。
- [ ] 手动调用 `/api/v1/agent/stream` 验证 SSE 阶段事件。
- [ ] 手动验证高风险症状触发安全降级。
## Phase 3.1: LangGraph Send 并行调度

- [x] LG-311 启用 `Send` 并行 worker 派发
  - Files: `app/agent/graph/graph.py`, `app/agent/graph/router.py`
  - Acceptance: `graph_dispatcher` 能将同一轮多个 ready task 派发到多个 worker 分支。
- [x] LG-312 增加并行 state reducer
  - Files: `app/agent/state.py`
  - Acceptance: `worker_events`、`evidence_items`、`tool_calls`、`agent_trace`、`task_results` 等并行分支输出可以安全合并。
- [x] LG-313 Worker 返回增量 patch
  - Files: `app/agent/graph/nodes.py`
  - Acceptance: worker 不再返回完整 state，避免并行分支覆盖未变更字段。
- [x] LG-314 Composer 避免重复工具调用
  - Files: `app/agent/graph/nodes.py`
  - Acceptance: 已有 worker 结果时，composer 只消费现有结果，不再进入旧 tool-calling loop 重复调用图片等工具。
- [x] LG-315 并行调度测试覆盖
  - Files: `tests/test_langgraph_agent.py`, `tests/test_agent_api.py`
  - Acceptance: 覆盖多 ready task 派发、`max_parallel_tasks`、`Send` 分支、composer 不重复工具调用，以及现有 Agent API 闭环。
