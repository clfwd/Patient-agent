# 阶段交接说明

最后同步日期：2026-05-27

## 当前已完成

- 患者、病历、就诊基础数据能力
- 图片上传与 `image_id` 引用
- MCP 工具注册与敏感工具身份核验
- 基于 Qwen 的病例图片分析
- 基于 Qwen Omni 的语音播报与本地 `mp3` 保存
- `POST /api/v1/agent/invoke` 同步 Agent 入口
- `POST /api/v1/agent/stream` SSE 流式 Agent 入口
- 会话级短期记忆持久化与恢复
- 聊天工作台会话、消息、附件接口
- 长期记忆第一阶段：抽取、事件/画像入库、job 重试
- 长期记忆基础召回：dense / keyword / RRF

## 当前 Agent 能力

当前 Agent 支持：

- LangChain tool-calling 优先
- 失败时回退启发式工具路由
- 结构化执行轨迹返回
- 会话短期记忆恢复
- 长期记忆摘要注入 prompt
- 自动生成音频

## 最近一次已验证状态

在 2026-05-27 本地运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

结果：

- 37 个测试全部通过

覆盖范围：

- 基础 API
- MCP
- TTS
- 图片上传与图像分析
- Agent tool-calling、流式、会话恢复
- 聊天工作台会话与附件
- 长期记忆抽取、重试、profile 覆盖与召回

## 当前仍未完成

- 正式鉴权 / 授权体系
- 完整审计日志
- 生产级文件清理与生命周期治理
- 删除基础业务资源的接口
- 多 Agent 协作

## 已知注意点

- `app.main` 当前仍使用 `@app.on_event("startup")` / `@app.on_event("shutdown")`，本地测试会出现 DeprecationWarning，但当前不影响功能。
- 源码中仍有部分历史乱码字符串，主要分布在少量 OpenAPI `summary` / `description` 和个别错误文案中，不影响主流程与测试，但会影响文档展示与中文可读性。
- 项目文档在 2026-05-27 已按当前代码重新对齐；如果继续推进记忆或前端工作台，需同步更新 `README.md`、`AGENTS.md`、`docs/integration-guide.md`、`docs/architecture.md`、`docs/runbook.md`。

## 下一阶段建议

建议优先推进：

1. 正式鉴权 / 授权体系
2. 关键操作审计日志
3. 生产级文件治理策略
4. 记忆召回效果评估与可观测性
5. 将 `on_event` 生命周期迁移到 FastAPI lifespan
