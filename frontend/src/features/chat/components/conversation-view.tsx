import { AgentStatusStrip } from "@/features/agent/components/agent-status-strip";
import { Composer } from "@/features/chat/components/composer";
import { MessageList } from "@/features/chat/components/message-list";
import { Panel } from "@/shared/ui/panel";
import type { ChatMessage, DraftAttachment, RunState, SessionItem, VerificationFields } from "@/shared/types/agent";

type ConversationViewProps = {
  title: string;
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
  onToggleAudio: () => void;
};

export function ConversationView({
  title,
  session,
  messages,
  draft,
  draftAttachments,
  verification,
  verificationExpanded,
  runState,
  audioEnabled,
  onDraftChange,
  onVerificationFieldChange,
  onToggleVerification,
  onFilesSelected,
  onRemoveDraftAttachment,
  onSubmit,
  onToggleAudio,
}: ConversationViewProps) {
  return (
    <Panel className="flex h-full min-h-0 flex-1 flex-col overflow-hidden px-5 py-5 sm:px-6">
      <div className="mb-5 shrink-0 border-b border-line/80 pb-4">
        <p className="text-xs uppercase tracking-[0.24em] text-muted">Workspace</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">{title}</h2>
        <p className="mt-2 text-sm text-muted">
          {session ? `会话 ID: ${session.id}` : "新会话将在首条消息发送后创建。"}
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {messages.length === 0 ? (
          <div className="mx-auto mt-16 max-w-xl text-center">
            <p className="text-sm uppercase tracking-[0.24em] text-muted">Patient-first AI Agent</p>
            <h3 className="mt-4 text-4xl font-semibold tracking-tight">把问诊、复诊、图片理解整合到一个自然对话界面里。</h3>
            <p className="mt-4 text-base leading-8 text-muted">
              这版界面优先保证长文本阅读、会话切换和图片提问体验，不走传统后台风格。
            </p>
          </div>
        ) : (
          <>
            <AgentStatusStrip runState={runState} />
            <MessageList messages={messages} />
          </>
        )}
      </div>

      <div className="shrink-0">
        <Composer
          audioEnabled={audioEnabled}
          disabled={runState.mode === "submitting" || runState.mode === "streaming"}
          draft={draft}
          draftAttachments={draftAttachments}
          verification={verification}
          verificationExpanded={verificationExpanded}
          onDraftChange={onDraftChange}
          onVerificationFieldChange={onVerificationFieldChange}
          onToggleVerification={onToggleVerification}
          onFilesSelected={onFilesSelected}
          onRemoveDraftAttachment={onRemoveDraftAttachment}
          onSubmit={onSubmit}
          onToggleAudio={onToggleAudio}
        />
      </div>
    </Panel>
  );
}
