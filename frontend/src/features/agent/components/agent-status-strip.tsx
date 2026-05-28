import type { RunState } from "@/shared/types/agent";

export function AgentStatusStrip({ runState }: { runState: RunState }) {
  const latest = runState.stages.at(-1);
  if (runState.mode === "idle" && !latest) {
    return null;
  }

  const label =
    runState.mode === "submitting" || runState.mode === "streaming"
      ? "Agent 正在处理"
      : runState.mode === "error"
        ? "Agent 执行失败"
        : "Agent 状态";

  return (
    <div className="mb-4 rounded-full border border-line bg-white/70 px-4 py-2 text-xs text-muted">
      <span className="font-medium text-foreground">{label}</span>
      {latest ? <span className="ml-2">{latest.stage} · {latest.detail}</span> : null}
    </div>
  );
}
