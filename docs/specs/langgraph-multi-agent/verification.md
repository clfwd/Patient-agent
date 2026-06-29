# Verification: LangGraph Multi-Agent 医疗助手

## Commands

Phase 0、Phase 1、Phase 2 和 Phase 3 已执行的检查与测试：

```text
Get-Content -Path AGENTS.md -TotalCount 220
Get-ChildItem -Path docs -Force | Select-Object Name,Mode,Length
Get-Content -Path app\agent\service.py -TotalCount 220
Get-Content -Path app\agent\schemas.py -TotalCount 220
Get-Content -Path requirements.txt
Get-Content -Path docs\architecture.md -TotalCount 200
.\.venv\Scripts\python.exe -m pip show langchain-core langgraph
.\.venv\Scripts\python.exe -m unittest tests.test_medical_knowledge tests.test_agent_api -v
.\.venv\Scripts\python.exe -m unittest tests.test_langgraph_agent tests.test_agent_api tests.test_medical_knowledge -v
.\.venv\Scripts\python.exe -m unittest tests.test_agent_api -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd frontend
npm run build
```

## Results

- 已完成 LG-001：`requirements.txt` 新增 `langgraph==0.2.34`。
- 已完成 LG-002：`README.md`、`docs/runbook.md`、`AGENTS.md` 已说明 graph 模式配置含义。
- 已完成 LG-101：新增 `app/agent/graph/`，包含固定 Phase 1 线性 graph。
- 已完成 LG-102：graph preflight 节点复用现有 `_preflight_node()`，并保持会话历史加载和 user message 持久化。
- 已完成 LG-103：`AGENT_GRAPH_ENABLED=false` 或 `missing_dependency_fallback` 时仍走旧链路。
- 已完成 LG-104：graph 路径输出 `graph_preflight`、`graph_router`、`graph_composer`、`graph_postprocess` trace stage，前端 `AgentTrace.stage` 已放宽为字符串。
- 已新增测试覆盖 graph enabled、graph fallback、graph 身份失败、默认关闭和强制依赖缺失。
- 已完成 LG-201：新增 `app/knowledge` 数据模型和仓储，使用主业务库自动建表。
- 已完成 LG-202：新增关键词检索服务，返回 `content`、`title`、`source`、`document_id`、`chunk_id`。
- 已完成 LG-203：LangGraph 路径新增 `graph_medical_knowledge` 节点，通用医学知识问题可触发检索并追加来源摘要。
- 已完成 LG-204：新增 `tests/fixtures/medical_knowledge_seed.json`，测试不依赖外部网络或真实医学数据库。
- 已完成 LG-301：规则优先 Planner 可生成 `task_board`，覆盖患者数据、医学知识、图片、长期记忆和高风险规则。
- 已完成 LG-302：LangGraph 路径新增 `graph_patient_data_agent`，复用现有患者、病历、就诊工具。
- 已完成 LG-303：LangGraph 路径新增 `graph_image_analysis_agent`，图片引用请求会调用现有图片分析工具。
- 已完成 LG-304：LangGraph 路径新增 `graph_memory_agent`，长期记忆召回从 graph preflight 拆为独立 worker。
- `.\.venv\Scripts\python.exe -m unittest tests.test_medical_knowledge tests.test_agent_api -v` 通过：20 个用例 OK。
- `.\.venv\Scripts\python.exe -m unittest tests.test_langgraph_agent tests.test_agent_api tests.test_medical_knowledge -v` 通过：27 个用例 OK。
- `.\.venv\Scripts\python.exe -m unittest tests.test_agent_api -v` 通过：14 个用例 OK（Phase 1 记录）。
- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` 通过：57 个用例 OK。
- `npm run build` 在 `frontend/` 下通过（Phase 1 记录，本阶段未改前端）。

## Manual Checks

- 检查 graph 路径仍复用现有 tool-calling / heuristic fallback。
- 检查 graph 路径不新增知识库、不新增数据库迁移、不改 MCP 工具语义。
- 检查 `used_models.graph_mode` 能标记 `disabled`、`available` 或 `missing_dependency_fallback`。
- 检查 Phase 2 不新增公开知识库管理 API。
- 检查无知识命中时不伪造 `参考来源`。
- 检查 Phase 3 graph 路径使用 `graph_planner -> graph_dispatcher -> worker -> graph_join -> graph_gap_checker` 主干。
- 检查 worker 不直接互相调用，任务状态由 Join 根据 `worker_events` 统一更新。
- 检查高风险问题只追加提示性风险文案，正式 Safety Agent 留到 Phase 4。

## Deviations

- Phase 2 没有实现 embedding、外部医学搜索、知识库管理 API、Safety Agent 或真正多路由。
- Phase 3 采用串行 task board 语义，尚未启用 LangGraph `Send` 并行派发。
- Phase 3 未实现正式 Safety Agent 或 Evidence Agent，仅产出 `risk_flags` 和结构化 `evidence_items`。

## Remaining Work

- 进入 Phase 4：接入 Evidence / Safety 节点。
- 后续可将 Dispatcher 从串行 ready task 调度切换为 `Send` 并行派发。
