import { AlertCircle, ChevronDown, ChevronUp, Check, Circle } from "lucide-react";
import { useState } from "react";

import { traceStageLabel } from "@/features/agent/agent-trace-labels";
import { AgentTraceList } from "@/features/agent/components/agent-trace-list";
import type { RunState } from "@/shared/types/agent";

export function AgentStatusStrip({ runState, onRetry }: { runState: RunState; onRetry?: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const latest = runState.stages.at(-1);
  if (runState.mode === "idle" && !latest) {
    return null;
  }

  const running = runState.mode === "submitting" || runState.mode === "streaming";
  const recentStages = runState.stages.slice(-3);

  return (
    <div className="mb-5 border-l-2 border-accent/35 pl-3.5">
      <div className="flex items-center gap-2 text-sm text-muted">
        {runState.mode === "error" ? (
          <AlertCircle className="h-4 w-4 text-[#b4533c]" />
        ) : running ? (
          <Circle className="h-3 w-3 fill-accent text-accent" />
        ) : (
          <Check className="h-4 w-4 text-[#4f6f62]" />
        )}
        <span className="font-medium text-foreground">
          {runState.mode === "error" ? "回答生成失败" : running ? "正在分析你的问题…" : "已完成分析"}
        </span>
        {!running && runState.mode !== "error" && latest?.created_at ? <span>· 已更新</span> : null}
      </div>

      {running ? (
        <div className="mt-2 space-y-1 text-sm text-muted">
          {recentStages.length ? recentStages.map((stage, index) => (
            <div key={`${stage.stage || stage.event}-${index}`} className="flex items-center gap-2">
              {stage.status === "completed" ? <Check className="h-3.5 w-3.5 text-[#4f6f62]" /> : <Circle className="h-2.5 w-2.5 fill-accent text-accent" />}
              <span>{traceStageLabel(stage)}</span>
            </div>
          )) : <span>正在建立安全连接</span>}
        </div>
      ) : null}

      {runState.stages.length ? (
        <>
          <button
            className="mt-2 inline-flex items-center gap-1 text-xs text-muted transition hover:text-foreground"
            onClick={() => setExpanded((current) => !current)}
            type="button"
          >
            {expanded ? "收起过程" : "查看过程"}
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
          {expanded ? <div className="mt-2 border-t border-line pt-2"><AgentTraceList stages={runState.stages} /></div> : null}
        </>
      ) : null}
      {runState.mode === "error" && onRetry ? (
        <button className="mt-2 text-xs font-medium text-foreground underline underline-offset-4" onClick={onRetry} type="button">
          重新尝试
        </button>
      ) : null}
    </div>
  );
}
