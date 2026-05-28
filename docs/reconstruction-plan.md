# Git 重建方案

最后更新：2026-05-29

## 目标

当前仓库缺少按功能模块逐步演进的 Git 历史。本方案用于在**不伪装为真实原始提交记录**的前提下，补一条可读、可展示、可交接的“模块化重建历史”。

本方案追求：

- 能看出项目功能是如何逐步长出来的
- 每个提交都对应清晰能力边界
- 每个阶段有可运行或可测试的验收点
- 保留当前完整快照，避免重建过程伤到现有代码

本方案不追求：

- 还原当时逐行真实开发过程
- 做到严格审计级别的历史真实性

## 重建原则

1. 所有补出来的提交都明确标注为 `[reconstructed]`
2. 当前完整状态先单独保存为快照分支
3. 模块切分优先，时间精度次之
4. 对跨阶段的大文件，只重建必要的阶段版本，不追求过细拆分
5. 每个提交都要有一句清楚的能力说明和一条验证方式

## 建议分支结构

- `snapshot/current`
  - 保存当前完整代码快照
- `reconstructed/main`
  - 从空历史或极小骨架开始，按模块逐步补提交

如后续需要对外展示，可将默认分支切到 `reconstructed/main`，并保留 `snapshot/current` 作为对照。

## 重建前检查

在执行重建前，先确认以下事项：

- 当前代码就是希望保留的最终快照
- `.gitignore` 需要补充忽略项，避免误收录本地环境与数据库文件
- 本地 `.venv` 可正常运行测试
- 接受“时间线为推断重建”的说明口径

当前建议补充到 `.gitignore` 的内容：

```gitignore
.venv/
.venv_py38_backup_20260510/
.idea/
patient_agent.db
```

## 当前可用线索

本仓库虽然没有 `.git`，但仍有足够线索支持重建：

- `docs/handoff.md` 给出了截至 2026-05-27 的阶段状态
- `README.md`、`AGENTS.md`、`docs/architecture.md` 给出了当前能力边界
- `app/` 与 `tests/` 文件的 `LastWriteTime` 可以帮助推断功能出现顺序

按当前时间线，大致可以归纳为：

- 2026-04-19：数据库与基础 API
- 2026-05-09 到 2026-05-12：TTS、图片上传、病例图分析、Agent 雏形
- 2026-05-21：MCP、工具路由、运行时环境
- 2026-05-23 到 2026-05-27：长期记忆、聊天工作台、文档对齐
- 2026-05-28：Agent 集成收口

## 推荐提交切分

### 1. `[reconstructed] chore: bootstrap project skeleton and runtime config`

目标：

- 建立最小项目骨架
- 引入基础依赖、数据库配置、包结构

建议纳入：

- `requirements.txt`
- `app/__init__.py`
- `app/db/__init__.py`
- `app/db/config.py`
- `app/db/database.py`
- 必要的空目录和包初始化文件

验证：

- 代码可导入
- 应用基础结构完整

### 2. `[reconstructed] feat: add patient medical record and visit CRUD`

目标：

- 落地患者、病历、就诊三类核心业务数据能力

建议纳入：

- `app/db/models.py` 的基础业务模型部分
- `app/db/repositories.py` 的基础 CRUD 部分
- `app/schemas.py`
- 基础 API 路由与主应用初版装配
- `tests/test_api.py`
- `tests/test_db_repositories.py`

验证：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_api.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_db_repositories.py" -v
```

### 3. `[reconstructed] feat: add tts service and api`

目标：

- 增加语音生成能力与文件访问接口

建议纳入：

- `app/tts/api.py`
- `app/tts/schemas.py`
- `app/tts/service.py`
- `tests/test_tts_api.py`

验证：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_tts_api.py" -v
```

### 4. `[reconstructed] feat: add image upload and case image analysis`

目标：

- 支持图片上传、图片读取、病例图片分析

建议纳入：

- `app/images/service.py`
- `app/mcp/qwen_client.py`
- 图片相关 API 与模型装配
- `tests/test_image_api.py`

验证：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_image_api.py" -v
```

### 5. `[reconstructed] feat: add mcp registry api and tool routing`

目标：

- 增加 MCP 工具注册、工具调用与启发式路由

建议纳入：

- `app/mcp/api.py`
- `app/mcp/router.py`
- `app/mcp/schemas.py`
- `app/tool_routing.py`
- `app/runtime_env.py`
- `app/agent/tools.py` 中与工具包装直接相关的稳定部分
- `tests/test_mcp_api.py`
- `tests/test_runtime_env.py`

验证：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_mcp_api.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_runtime_env.py" -v
```

### 6. `[reconstructed] feat: add long-term memory extraction storage and retrieval`

目标：

- 增加长期记忆抽取、存储、job 重试与基础召回

建议纳入：

- `app/memory/db.py`
- `app/memory/models.py`
- `app/memory/repositories.py`
- `app/memory/schemas.py`
- `app/memory/service.py`
- `app/memory/worker.py`
- `app/memory/extractor.py`
- `app/memory/embedding.py`
- `app/memory/retrieval.py`
- `tests/test_memory_api.py`
- `tests/test_memory_retrieval.py`

验证：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_memory_api.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_memory_retrieval.py" -v
```

### 7. `[reconstructed] feat: add chat workspace sessions messages and attachments`

目标：

- 增加聊天工作台的会话、消息、附件能力

建议纳入：

- `app/db/models.py` 中 chat 相关模型
- `app/db/repositories.py` 中 chat 相关仓储
- `app/agent/schemas.py` 中会话上下文字段
- `tests/test_chat_workspace_api.py`

验证：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_chat_workspace_api.py" -v
```

### 8. `[reconstructed] feat: integrate agent invoke stream memory and audio postprocess`

目标：

- 将 Agent、短期记忆、长期记忆注入、工具调用、音频后处理整合为当前主链路

建议纳入：

- `app/agent/api.py`
- `app/agent/service.py`
- `app/agent/schemas.py`
- `app/agent/state.py`
- `app/main.py`
- `app/error_handling.py`
- `tests/test_agent_api.py`

验证：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_agent_api.py" -v
```

### 9. `[reconstructed] docs: sync readme architecture runbook and handoff`

目标：

- 将文档与当前代码边界同步

建议纳入：

- `README.md`
- `AGENTS.md`
- `docs/architecture.md`
- `docs/integration-guide.md`
- `docs/runbook.md`
- `docs/handoff.md`

验证：

- 文档描述与当前代码一致
- 不把 PRD 中未实现能力误写成已完成

## 关键难点与处理方式

### 1. 聚合文件跨多个阶段

以下文件大概率需要分阶段重建，而不是一次性直接放入：

- `app/main.py`
- `app/db/models.py`
- `app/db/repositories.py`
- `app/agent/service.py`
- `app/agent/schemas.py`

处理原则：

- 不用追求逐行真实历史
- 每个阶段只保留当时“足够成立”的最小版本
- 后续阶段再补字段、补模型、补装配

### 2. 避免依赖交互式 Git 操作

不建议把重建流程建立在 `git add -p` 上。更稳妥的方式是：

- 以 `snapshot/current` 作为完整参考
- 在 `reconstructed/main` 上按阶段恢复指定文件
- 对跨阶段的大文件直接写出阶段版本，再提交

### 3. 测试不是每一步都必须全绿

中间阶段只需要保证**该阶段目标相关测试**尽量成立。最终阶段需要跑一次全量测试。

全量验证命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 推荐执行流程

### 步骤 0：先保护当前快照

```powershell
git init
git checkout -b snapshot/current
```

先检查 `.gitignore`，再提交当前完整状态：

```powershell
git add .
git commit -m "[reconstructed] snapshot: current workspace baseline before history rebuild"
```

### 步骤 1：新建重建分支

```powershell
git checkout --orphan reconstructed/main
git rm -rf .
```

说明：

- 这里会在 **Git 索引层面** 清空工作树，用于从空历史开始重建
- 只有在 `snapshot/current` 已经提交完成后，才允许执行

如担心操作风险，可先复制整个目录到旁路工作区，再执行本流程。

### 步骤 2：按阶段恢复文件并提交

推荐模式：

1. 从 `snapshot/current` 检出该阶段可以完整复用的文件
2. 对跨阶段文件手工写出最小阶段版
3. 运行该阶段对应测试
4. 提交并写明验证口径

示例：

```powershell
git checkout snapshot/current -- requirements.txt app/__init__.py app/db/__init__.py app/db/config.py app/db/database.py
git add requirements.txt app/__init__.py app/db/__init__.py app/db/config.py app/db/database.py
git commit -m "[reconstructed] chore: bootstrap project skeleton and runtime config"
```

### 步骤 3：最终跑全量测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### 步骤 4：打标签

```powershell
git tag reconstructed-v1
```

## 对外说明建议

可在仓库说明或首个重建提交中明确写出：

> 本仓库 Git 历史为后补的模块化重建历史，用于体现功能演进顺序；不是开发过程中的原始逐次提交记录。

## 完成标准

满足以下条件即可认为重建完成：

- `snapshot/current` 保存了当前完整快照
- `reconstructed/main` 至少有 8 到 9 个清晰模块提交
- 提交顺序与当前模块演进逻辑一致
- 最终全量测试通过
- 文档中明确标注该历史为重建历史

## 下一步建议

建议按以下顺序执行：

1. 先补 `.gitignore`
2. 初始化 Git 并保存 `snapshot/current`
3. 从第 1 到第 3 个提交开始试切，验证切分粒度是否自然
4. 再处理 `memory`、`chat workspace`、`agent` 三个后期集成模块

如果执行过程中发现阶段文件切分过于别扭，优先**合并相邻提交**，不要为了凑提交数而过度伪造细节。
