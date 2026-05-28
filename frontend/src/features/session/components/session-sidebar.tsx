import { MessageSquarePlus } from "lucide-react";

import { Button } from "@/shared/ui/button";
import { Panel } from "@/shared/ui/panel";
import type { SessionItem } from "@/shared/types/agent";

type SessionSidebarProps = {
  sessions: SessionItem[];
  activeSessionId?: string;
  loading: boolean;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
};

export function SessionSidebar({
  sessions,
  activeSessionId,
  loading,
  onSelectSession,
  onNewSession,
}: SessionSidebarProps) {
  return (
    <Panel className="hidden h-full min-h-0 w-[300px] shrink-0 flex-col p-4 lg:flex">
      <div className="mb-5 shrink-0">
        <p className="text-xs uppercase tracking-[0.24em] text-muted">Patient Agent</p>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight">患者端智能工作台</h1>
      </div>

      <Button className="mb-5 w-full shrink-0 justify-start gap-2" onClick={onNewSession}>
        <MessageSquarePlus className="h-4 w-4" />
        新对话
      </Button>

      <div className="mb-3 flex shrink-0 items-center justify-between text-xs uppercase tracking-[0.22em] text-muted">
        <span>会话</span>
        {loading ? <span>加载中</span> : <span>{sessions.length}</span>}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        <div className="flex flex-col gap-2">
          {sessions.map((session) => (
            <button
              key={session.id}
              className={`rounded-[22px] border px-3 py-3 text-left transition ${
                session.id === activeSessionId
                  ? "border-foreground/15 bg-foreground text-white"
                  : "border-transparent bg-white/60 hover:border-line hover:bg-white"
              }`}
              onClick={() => onSelectSession(session.id)}
              type="button"
            >
              <div className="line-clamp-1 text-sm font-medium">{session.title || "未命名会话"}</div>
              <div className={`mt-1 line-clamp-2 text-xs ${session.id === activeSessionId ? "text-white/75" : "text-muted"}`}>
                {session.last_message_preview || "等待第一条消息"}
              </div>
            </button>
          ))}
        </div>
      </div>
    </Panel>
  );
}
