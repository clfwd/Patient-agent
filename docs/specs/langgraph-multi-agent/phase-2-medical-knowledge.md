# Phase 2: Medical Knowledge Agent 最小闭环

## 目标

Phase 2 只实现本地医疗知识关键词检索的最小闭环：

- 本地医疗知识 document / chunk 入库
- 基于关键词的稳定检索
- LangGraph 路径中新增 `graph_medical_knowledge` 节点
- 最终回答追加简短来源摘要

本阶段不实现 embedding、外部医学搜索、知识库管理 API、Safety Agent 或真正 Supervisor 分流。

## 表结构

### `medical_knowledge_documents`

- `id`: `String(36)`，主键
- `title`: `String(255)`，知识文档标题
- `source`: `String(255)`，来源标识，例如院内宣教文档、测试 fixture、指南名称
- `source_type`: `String(64)`，默认 `manual`
- `content`: `Text`，原始文档正文
- `metadata_json`: `Text`，可选扩展元数据
- `created_at`: `FlexibleDateTime`
- `updated_at`: `FlexibleDateTime`

### `medical_knowledge_chunks`

- `id`: `String(36)`，主键
- `document_id`: `String(36)`，关联 `medical_knowledge_documents.id`
- `chunk_index`: `Integer`，文档内顺序
- `content`: `Text`，chunk 正文
- `metadata_json`: `Text`，可选 chunk 元数据
- `search_text`: `Text`，关键词检索文本
- `created_at`: `FlexibleDateTime`

## 检索策略

- 使用主业务数据库，不新增 `KNOWLEDGE_DATABASE_URL`
- 第一版只做 Python 关键词评分，保证 SQLite 和 PostgreSQL 行为一致
- 英文按小写单词 token 匹配
- 中文按连续中文短语和二字片段匹配
- 返回字段固定为：
  - `content`
  - `title`
  - `source`
  - `document_id`
  - `chunk_id`

## Graph 接入

- 新增节点名：`graph_medical_knowledge`
- Router 命中通用医学知识关键词时，将节点插入到 `graph_router` 与 `graph_composer` 之间
- 节点执行：
  1. 调用 `MedicalKnowledgeService.search(message, limit=3)`
  2. 写入 `state["knowledge_hits"]`
  3. 写入 `state["knowledge_retrieval_mode"]`
  4. 记录 `agent_trace`
- Composer 仍复用现有 `_tool_calling_node()`，但若 `knowledge_hits` 非空，在最终回答末尾追加：

```text
参考来源：
- <title> - <source>
```

## 测试数据

测试 fixture 位于 `tests/fixtures/medical_knowledge_seed.json`，只包含人工编写的最小测试知识：

- 血糖基础知识
- 血压基础知识
- 发热护理

测试不依赖外部网络或真实医学数据库。

## 边界

- legacy 单 Agent 路径不触发医疗知识检索
- 无命中时不伪造来源
- 不改变 `AgentInvokeResponse` schema
- 不新增公开知识库管理接口
