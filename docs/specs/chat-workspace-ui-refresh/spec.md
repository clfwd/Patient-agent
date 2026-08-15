# Spec: Chat Workspace UI Refresh

## SDD State

- Level: Large
- Stage: Approved for implementation
- Approved Stages: Spec, Design, Tasks (user explicitly requested the complete implementation sequence)
- Feature: chat-workspace-ui-refresh
- Next Gate: Implementation and verification
- Verification:
  - Planned: TypeScript build plus visual and interaction review of existing API/SSE flows.
  - Result: Not run yet

## Background

现有工作台保留了会话、附件、身份核验和 SSE Agent 流，但以圆角卡片和暖色面板为主，阅读区狭窄，Agent 轨迹与消息脱节。

## Goal

在不改变任何后端契约的前提下，重构为克制、专业、以连续对话阅读为核心的医疗 Agent Chat 工作台。

## Scope

- 三栏 App Shell、响应式 Drawer 与右侧 Inspector 折叠。
- 扁平会话列表、紧凑 Header、宽正文消息流与紧凑 Composer。
- 将 SSE 阶段轨迹融入当前 assistant 消息，提供收起摘要和展开过程。
- 近底部自动跟随、上翻时停止跟随与“回到最新消息”。
- 保留图片预览、身份核验、音频、历史会话、同步回退，并为已有请求增加纯前端重试入口。

## Non-goals

- 不修改 API、数据库、SSE event/payload、后端状态枚举或 Agent Runtime。
- 不接入当前工作台未使用的任务式 `/agent/tasks` 恢复接口。
- 不引入新的 UI 或 Markdown 第三方依赖。

## Functional Requirements

- 现有 `session.created`、`agent.phase`、`answer.delta`、`answer.done`、`agent.error` 继续由同一 API 模块解析和驱动 UI。
- Agent 只展示阶段、能力和完成/失败状态，不显示模型推理文本。
- 长回答只由消息区统一滚动，assistant message 自身不产生滚动容器。
- 宽屏三栏；中屏右栏 Drawer；小屏两侧均为 Drawer。

## Acceptance Criteria

- [ ] API request body、路径、方法、SSE event 名与 payload 解析保持兼容。
- [ ] 用户消息、流式 answer delta、完成、错误、同步回退、会话切换、附件上传和身份核验仍可用。
- [ ] 视觉上不再由暖色大卡片与大圆角主导，中心正文可连续阅读。
- [ ] 页面可构建通过 TypeScript 与 Vite 校验。

## Assumptions

- 会话列表只有现有 `updated_at`，按本地日期分为“今天 / 昨天 / 更早”。
- 当前 API 的 trace `detail` 不作为安全的用户文案；新 UI 使用受控阶段标签展示。
