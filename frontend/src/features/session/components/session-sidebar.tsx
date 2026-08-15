import { MessageSquarePlus, X } from "lucide-react";

import { Button } from "@/shared/ui/button";
import type { SessionItem } from "@/shared/types/agent";

type SessionSidebarProps = {
  sessions: SessionItem[]; activeSessionId?: string; loading: boolean; mobileOpen: boolean;
  onSelectSession: (id: string) => void; onNewSession: () => void; onCloseMobile: () => void;
};

function groupSessions(sessions: SessionItem[]) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
  const groups: Array<[string, SessionItem[]]> = [["今天", []], ["昨天", []], ["更早", []]];
  sessions.forEach((session) => {
    const updated = new Date(session.updated_at); updated.setHours(0, 0, 0, 0);
    groups[updated >= today ? 0 : updated >= yesterday ? 1 : 2][1].push(session);
  });
  return groups.filter(([, items]) => items.length);
}

export function SessionSidebar({ sessions, activeSessionId, loading, mobileOpen, onSelectSession, onNewSession, onCloseMobile }: SessionSidebarProps) {
  const groups = groupSessions(sessions);
  const content = (
    <>
      <div className="flex items-center justify-between px-2 pb-5 pt-1"><div><p className="text-xs font-medium text-muted">患者智能助手</p><h1 className="mt-1 text-[15px] font-semibold text-foreground">会话</h1></div><button aria-label="关闭会话列表" className="rounded-md p-1.5 text-muted hover:bg-black/[0.04] md:hidden" onClick={onCloseMobile} type="button"><X className="h-4 w-4" /></button></div>
      <Button className="mb-5 w-full justify-start gap-2" onClick={onNewSession}><MessageSquarePlus className="h-4 w-4" />新对话</Button>
      <div className="min-h-0 flex-1 overflow-y-auto"><div className="space-y-5 px-1">{loading ? <p className="px-2 text-sm text-muted">加载会话中…</p> : groups.length ? groups.map(([label, items]) => <section key={label}><p className="mb-1.5 px-2 text-xs font-medium text-muted">{label}</p><div className="space-y-0.5">{items.map((session) => <button key={session.id} className={`w-full rounded-md px-2.5 py-2 text-left text-sm transition ${session.id === activeSessionId ? "bg-[#e9eaec] font-medium text-foreground" : "text-foreground hover:bg-black/[0.04]"}`} onClick={() => { onSelectSession(session.id); onCloseMobile(); }} type="button"><span className="block truncate">{session.title || "未命名会话"}</span></button>)}</div></section>) : <p className="px-2 text-sm leading-6 text-muted">还没有会话。发送第一条消息后，会话会显示在这里。</p>}</div></div>
    </>
  );

  return <><aside className="hidden h-full w-[264px] shrink-0 flex-col border-r border-line bg-[#f7f7f8] p-3 md:flex">{content}</aside>{mobileOpen ? <div className="fixed inset-0 z-40 md:hidden"><button aria-label="关闭会话列表" className="absolute inset-0 bg-black/20" onClick={onCloseMobile} type="button" /><aside className="relative flex h-full w-[280px] flex-col bg-[#f7f7f8] p-3 shadow-xl">{content}</aside></div> : null}</>;
}
