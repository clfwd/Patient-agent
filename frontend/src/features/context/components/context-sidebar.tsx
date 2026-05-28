import { Panel } from "@/shared/ui/panel";
import type { RunState, SessionContext } from "@/shared/types/agent";

export function ContextSidebar({ context, runState }: { context?: SessionContext; runState: RunState }) {
  return (
    <div className="hidden h-full min-h-0 w-[320px] shrink-0 overflow-y-auto xl:flex xl:flex-col xl:gap-4">
      <Panel className="p-5">
        <p className="text-xs uppercase tracking-[0.24em] text-muted">患者摘要</p>
        {context?.patient ? (
          <div className="mt-4 space-y-2 text-sm leading-7 text-muted">
            {Object.entries(context.patient).slice(0, 6).map(([key, value]) => (
              <div key={key} className="flex items-start justify-between gap-3">
                <span className="text-foreground">{key}</span>
                <span className="text-right">{String(value ?? "-")}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-sm leading-7 text-muted">会话尚未绑定患者，发送问题并完成身份校验后会显示摘要。</p>
        )}
      </Panel>

      <Panel className="p-5">
        <p className="text-xs uppercase tracking-[0.24em] text-muted">会话状态</p>
        <div className="mt-4 space-y-2 text-sm text-muted">
          <div>会话: {context?.session.title || "未命名"}</div>
          <div>状态: {context?.session.status || "new"}</div>
          <div>附件: {context?.attachments.length ?? 0}</div>
        </div>
      </Panel>

      <Panel className="p-5">
        <p className="text-xs uppercase tracking-[0.24em] text-muted">Agent 轨迹</p>
        <div className="mt-4 space-y-3">
          {runState.stages.length === 0 ? (
            <p className="text-sm leading-7 text-muted">等待第一次执行。</p>
          ) : (
            runState.stages.map((stage, index) => (
              <div key={`${stage.stage}-${index}`} className="rounded-2xl border border-line bg-white/70 px-3 py-3">
                <div className="text-sm font-medium text-foreground">{stage.stage || stage.event}</div>
                <div className="mt-1 text-xs uppercase tracking-[0.2em] text-muted">{stage.status}</div>
                <div className="mt-2 text-sm leading-6 text-muted">{stage.detail}</div>
              </div>
            ))
          )}
        </div>
      </Panel>
    </div>
  );
}
