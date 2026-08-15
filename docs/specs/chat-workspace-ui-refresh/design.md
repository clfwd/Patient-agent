# Design: Chat Workspace UI Refresh

## SDD State

- Level: Large
- Stage: Approved for implementation
- Approved Stages: Spec, Design, Tasks
- Feature: chat-workspace-ui-refresh
- Next Gate: Implementation and verification
- Verification:
  - Planned: `npm run build` and focused manual interaction review.
  - Result: Not run yet

## Design Goals

- 用排版、留白和低对比表面分层，不用 card mosaic。
- Chat 是唯一主要工作面；患者信息是可收起 Inspector。
- 保持现有 Hook/API 为事实源，新增视图状态不穿透到后端。

## Overview

`WorkspacePage` 管理两侧 Drawer/Inspector 开合；`ConversationView` 提供 Header、统一滚动消息区与固定 Composer；`MessageList` 将当前 run 的安全摘要嵌入最新 assistant 消息。`useAgentWorkspace` 保留原 API 调用和 SSE 处理，只缓存已上传后的失败请求以支持重试。

## Modules

- `session-sidebar.tsx`: 日期分组扁平会话导航和移动 Drawer。
- `conversation-view.tsx`: 中心布局、Header、滚动容器与面板触发器。
- `message-list.tsx` / `markdown-answer.tsx`: 文档式消息、轻量 Markdown 和自动跟随。
- `agent-status-strip.tsx` / `agent-trace-list.tsx`: 内联阶段摘要与展开轨迹。
- `composer.tsx`: 72px 起始高度、附件缩略图及紧凑核验横幅。
- `context-sidebar.tsx`: 低权重 Inspector、隐私脱敏和 Drawer。

## API / Interface Design

所有现有 `shared/api/*` 的 URL、method、payload 和 SSE parser 保持不动。Hook 新增的重试只复用已构建的 `InvokePayload`，不增加请求字段。

## Risks And Tradeoffs

- 不引入 Markdown 库，使用受控轻量渲染，覆盖标题、列表、粗体、代码与简单表格；复杂 Markdown 将安全地退化为文本。
- 当前流式接口不支持 replay，因此不宣称任务级断线恢复；保持当前同步回退。
