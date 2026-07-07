# Spec: LangGraph Multi-Agent 医疗助手

## Background

当前后端已经有基于工具的单 Agent 编排，主链路集中在 `app/agent/service.py`，形态为 `preflight -> tool_calling -> postprocess`。该链路已经接入患者资料、病历、就诊记录、图片分析、长期记忆、语音后处理和会话持久化。

下一阶段希望将该链路改造成基于 LangGraph 的多节点、多 Agent 工作流，让身份核验、路由、患者数据读取、医疗知识检索、图片分析、长期记忆召回、安全校验和最终回答组合拥有更清晰的职责边界。

## Goal

在保持现有 `/api/v1/agent/invoke` 与 `/api/v1/agent/stream` 接口兼容的前提下，引入 LangGraph 编排骨架，并优先落地医疗知识检索 Agent，使最终回答可以同时结合患者上下文、长期记忆、附件分析和可追溯的医学知识依据。

## Scope

- 新增 LangGraph 编排层，作为 `PatientAgentService` 内部可切换的执行路径。
- 保留现有单 Agent 工具调用路径作为回退能力。
- 将现有能力拆成明确节点：
  - `Identity / Preflight`
  - `Supervisor / Router`
  - `Patient Data Agent`
  - `Medical Knowledge Agent`
  - `Image Analysis Agent`
  - `Memory Agent`
  - `Evidence / Safety Agent`
  - `Answer Composer Agent`
  - `Postprocess`
- 新增医疗知识检索的最小能力：
  - 医疗知识文档存储
  - 关键词或向量召回
  - 引用来源返回
  - 最终回答中区分患者事实、医学知识和安全提醒
- 保持现有前端工作台的请求结构、SSE 事件类型和右侧轨迹展示基本可用。

## Non-goals

- 不在第一阶段实现正式登录态、权限平台或完整审计系统。
- 不实现面向全院、多角色、多租户的完整医疗 Agent 平台。
- 不让多个 Agent 自由对话或无约束互相调用。
- 不直接给出诊断结论、处方结论或替代医生决策。
- 不在第一阶段引入复杂知识图谱、指南自动更新或外部互联网实时医学搜索。

## Users And Scenarios

- 患者：上传检查报告或描述症状，获得结合自身病历与通用医学知识的解释。
- 医护辅助人员：查看患者近期病历、就诊记录和长期记忆，快速整理问诊线索。
- 开发者：通过结构化 trace 观察每个 Agent 节点是否执行、调用了哪些工具、引用了哪些知识来源。

典型场景：

1. 用户询问“我的血糖最近是不是偏高，需要注意什么？”
2. 系统核验身份并读取患者资料、病历和就诊记录。
3. Medical Knowledge Agent 检索血糖指标解释、糖尿病风险、生活方式建议等知识片段。
4. Evidence / Safety Agent 检查回答是否存在无依据诊断或高风险医疗建议。
5. Answer Composer Agent 输出面向患者的解释，并标明“根据你的记录”和“通用医学知识”。

## Functional Requirements

- 系统必须兼容现有 `AgentInvokeRequest` 和 `AgentInvokeResponse`。
- 系统必须保留现有身份核验和患者归属校验语义。
- Supervisor 必须根据用户问题决定是否需要患者数据、医学知识、图片分析和长期记忆。
- Patient Data Agent 必须复用现有 `patient.*`、`medical_record.*`、`visit.*` 工具。
- Image Analysis Agent 必须复用现有图片附件解析和 `image.analyze_uploaded_image` 能力。
- Memory Agent 必须复用现有长期记忆召回能力。
- Medical Knowledge Agent 必须返回知识片段、来源元数据和置信度或排序信息。
- Evidence / Safety Agent 必须能标记高风险医疗问题，并要求最终回答降级为就医提醒或谨慎建议。
- Answer Composer Agent 必须汇总各节点结果，避免暴露完整思维链。
- SSE 流必须继续返回阶段事件，阶段名称可以扩展为 LangGraph 节点名称。

## Non-functional Requirements

- 默认路径应可在没有真实 LLM 或 LangGraph 依赖不可用时回退到现有启发式逻辑。
- 单轮请求的工具调用次数仍应受上限控制，避免无限循环。
- Trace 必须可读、可测试，但不得包含完整模型思维链。
- 医疗知识召回结果必须可追溯到本地来源，不能伪造引用。
- 多 Agent 编排不能绕过现有身份核验、患者上下文一致性和附件归属校验。
- 第一阶段优先稳定性和可解释性，不追求复杂自治。

## Core Flow

1. API 接收现有 Agent 请求。
2. `Identity / Preflight` 恢复或创建会话，解析附件，执行身份核验，构建初始状态。
3. `Supervisor / Router` 根据输入和上下文生成节点执行计划。
4. 按计划执行 Patient Data、Medical Knowledge、Image Analysis、Memory 等节点。
5. `Evidence / Safety` 检查候选证据和高风险医疗场景。
6. `Answer Composer` 生成最终回答和结构化 trace。
7. `Postprocess` 持久化消息，可选生成语音，触发长期记忆 job。
8. API 返回现有响应结构，SSE 按阶段推送事件。

## Edge Cases

- 身份核验失败：必须返回现有 `403` 语义，不继续执行敏感节点。
- 用户只问通用医学知识：可以调用 Medical Knowledge Agent，但不得读取患者敏感数据。
- 用户问题需要患者数据但缺少核验字段：必须要求补充核验信息。
- 知识库无结果：最终回答必须说明未找到本地知识依据，并避免编造来源。
- 图片附件不可访问或不属于当前会话：必须返回现有附件错误语义。
- 高风险症状：最终回答必须优先建议及时就医，不输出确定诊断。
- LangGraph 或 LLM 初始化失败：必须回退到现有单 Agent 或启发式路径。

## Acceptance Criteria

- [ ] 现有 Agent API 请求和响应结构保持兼容。
- [ ] 无 LangGraph 配置时，现有测试仍能通过。
- [ ] 打开 LangGraph 路径后，至少能完成“患者资料 + 医疗知识检索 + 最终回答”的闭环。
- [ ] 医疗知识回答包含来源信息，不伪造引用。
- [ ] 身份核验失败、患者归属不一致和附件归属错误仍返回现有错误语义。
- [ ] SSE 能展示 LangGraph 节点阶段。
- [ ] 高风险医疗问题会触发 Safety 节点降级策略。
- [ ] 新增或更新测试覆盖路由、知识检索、安全降级和回退路径。

## Assumptions

- 第一阶段以本地知识库为准，不接入外部实时医学搜索。
- 医疗知识库可以先使用 SQLite 或 PostgreSQL 中的简单表结构，后续再扩展向量库。
- `langgraph` 将作为新增依赖引入，但需要保留依赖缺失时的回退逻辑。
- 前端第一阶段只消费扩展后的 trace，不新增复杂可视化。
- 当前工作先设计规格，不直接修改运行时代码。

## Open Questions

- 医疗知识库第一批内容来源是什么：指南、药品说明书、院内宣教文档，还是人工整理的 FAQ？
- 医疗知识检索第一阶段是否必须使用 embedding，还是先用关键词检索即可？
- Safety 节点的风险分级规则是否采用固定规则、LLM 判断，还是二者结合？
- 前端是否需要单独展示知识来源，还是先放在最终回答和 Agent 轨迹里？
