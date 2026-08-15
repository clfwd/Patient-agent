import { Menu, PanelRightOpen, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Composer } from "@/features/chat/components/composer";
import { MessageList } from "@/features/chat/components/message-list";
import type { ChatMessage, DraftAttachment, RunState, SessionItem, VerificationFields } from "@/shared/types/agent";

type ConversationViewProps = {
  title: string;
  patientName?: string;
  session?: SessionItem;
  messages: ChatMessage[];
  draft: string;
  draftAttachments: DraftAttachment[];
  verification: VerificationFields;
  verificationExpanded: boolean;
  runState: RunState;
  audioEnabled: boolean;
  onDraftChange: (value: string) => void;
  onVerificationFieldChange: (field: keyof VerificationFields, value: string) => void;
  onToggleVerification: () => void;
  onFilesSelected: (files: FileList | null) => void;
  onRemoveDraftAttachment: (id: string) => void;
  onSubmit: () => void;
  onRetry: () => void;
  onToggleAudio: () => void;
  onOpenSidebar: () => void;
  onOpenContext: () => void;
};

export function ConversationView({ title, patientName, session, messages, draft, draftAttachments, verification, verificationExpanded, runState, audioEnabled, onDraftChange, onVerificationFieldChange, onToggleVerification, onFilesSelected, onRemoveDraftAttachment, onSubmit, onRetry, onToggleAudio, onOpenSidebar, onOpenContext }: ConversationViewProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const shouldFollowRef = useRef(true);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);

  useEffect(() => {
    if (shouldFollowRef.current) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "auto" });
  }, [messages, runState.mode, runState.stages.length]);

  function handleScroll() {
    const container = scrollRef.current;
    if (!container) return;
    const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 96;
    shouldFollowRef.current = nearBottom;
    setShowJumpToLatest(!nearBottom);
  }

  function jumpToLatest() {
    shouldFollowRef.current = true;
    setShowJumpToLatest(false);
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }

  return (
    <main className="flex min-w-0 flex-1 flex-col bg-white">
      <header className="flex h-[68px] shrink-0 items-center gap-3 border-b border-line px-4 sm:px-6">
        <button aria-label="打开会话列表" className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-black/[0.04] hover:text-foreground md:hidden" onClick={onOpenSidebar} type="button"><Menu className="h-4 w-4" /></button>
        <div className="min-w-0 flex-1"><h1 className="truncate text-[15px] font-semibold text-foreground sm:text-base">{title}</h1><p className="mt-0.5 truncate text-xs text-muted">{patientName ? `患者：${patientName}` : "未绑定患者"} · {session ? `会话状态：${session.status}` : "新会话"}</p></div>
        <button aria-label="打开患者信息" className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-black/[0.04] hover:text-foreground xl:hidden" onClick={onOpenContext} type="button"><PanelRightOpen className="h-4 w-4" /></button>
      </header>
      <div className="relative min-h-0 flex-1">
        <div ref={scrollRef} className="h-full overflow-y-auto" onScroll={handleScroll}>
          {messages.length === 0 ? <div className="mx-auto flex max-w-[760px] flex-col px-6 pt-[15vh] sm:px-10"><div className="mb-5 flex h-9 w-9 items-center justify-center rounded-lg bg-[#eef3f7] text-accent"><Sparkles className="h-4 w-4" /></div><p className="text-sm text-muted">患者智能助手</p><h2 className="mt-3 max-w-xl text-3xl font-semibold leading-tight tracking-tight text-foreground sm:text-4xl">从你最关心的健康问题开始。</h2><p className="mt-4 max-w-xl text-[15px] leading-7 text-muted">可以咨询复诊情况、上传图片，或让助手协助整理已经确认的患者信息。</p></div> : <MessageList messages={messages} runState={runState} onRetry={onRetry} />}
        </div>
        {showJumpToLatest ? <button className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full border border-line bg-white px-3 py-1.5 text-xs text-foreground shadow-sm transition hover:bg-surface" onClick={jumpToLatest} type="button">↓ 回到最新消息</button> : null}
      </div>
      <div className="shrink-0 border-t border-line bg-white px-4 pb-4 pt-3 sm:px-6"><div className="mx-auto max-w-[900px]"><Composer audioEnabled={audioEnabled} disabled={runState.mode === "submitting" || runState.mode === "streaming"} draft={draft} draftAttachments={draftAttachments} verification={verification} verificationExpanded={verificationExpanded} onDraftChange={onDraftChange} onVerificationFieldChange={onVerificationFieldChange} onToggleVerification={onToggleVerification} onFilesSelected={onFilesSelected} onRemoveDraftAttachment={onRemoveDraftAttachment} onSubmit={onSubmit} onToggleAudio={onToggleAudio} /></div></div>
    </main>
  );
}
