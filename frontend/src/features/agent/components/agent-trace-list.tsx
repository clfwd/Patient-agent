import { AlertCircle, Check, Circle } from "lucide-react";

import { traceStageLabel } from "@/features/agent/agent-trace-labels";
import type { AgentTrace } from "@/shared/types/agent";

export function AgentTraceList({ stages }: { stages: AgentTrace[] }) {
  if (stages.length === 0) {
    return <p className="text-sm leading-7 text-muted">等待第一次执行。</p>;
  }

  return (
    <div className="space-y-1.5">
      {stages.map((stage, index) => (
        <div key={`${stage.stage || stage.event}-${stage.status}-${index}`} className="flex items-center gap-2 py-1 text-sm text-muted">
          {stage.status === "failed" ? (
            <AlertCircle className="h-4 w-4 shrink-0 text-[#b4533c]" />
          ) : stage.status === "completed" ? (
            <Check className="h-4 w-4 shrink-0 text-[#4f6f62]" />
          ) : (
            <Circle className="h-3 w-3 shrink-0 fill-accent text-accent" />
          )}
          <span>{traceStageLabel(stage)}</span>
          {stage.status === "failed" ? <span className="text-[#a14a35]">暂时不可用</span> : null}
        </div>
      ))}
    </div>
  );
}
