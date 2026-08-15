# Tasks: Chat Workspace UI Refresh

## SDD State

- Level: Large
- Stage: Complete
- Approved Stages: Spec, Design, Tasks
- Feature: chat-workspace-ui-refresh
- Next Gate: Verification
- Verification:
  - Planned: build and focused manual checks.
  - Result: Passed

## Phase 1: Shell and visual system

- [x] T1 Replace warm card-based surface system with neutral chat workspace layout.
  - Files: `frontend/src/index.css`, `tailwind.config.ts`, shared UI, workspace and panel components.
  - Acceptance: narrow, low-chrome panels and responsive drawers.

## Phase 2: Conversation interaction

- [x] T2 Rework sidebar, messages, inline trace, composer and Inspector.
  - Files: `frontend/src/features/**`.
  - Acceptance: all existing presentation features remain available in the new hierarchy.

- [x] T3 Add client-only retry and non-intrusive scroll follow state.
  - Files: `use-agent-workspace.ts`, chat components.
  - Acceptance: no backend contract change.

## Verification

- [x] T4 Run `npm run build` and inspect the changed API/SSE call sites.
