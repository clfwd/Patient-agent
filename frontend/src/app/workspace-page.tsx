import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ConversationView } from "@/features/chat/components/conversation-view";
import { useAgentWorkspace } from "@/features/chat/hooks/use-agent-workspace";
import { ContextSidebar } from "@/features/context/components/context-sidebar";
import { SessionSidebar } from "@/features/session/components/session-sidebar";

export function WorkspacePage() {
  const navigate = useNavigate();
  const { sessionId } = useParams();
  const workspace = useAgentWorkspace(sessionId);

  const title = useMemo(() => workspace.activeSession?.title || "患者端智能助手", [workspace.activeSession?.title]);

  return (
    <div className="h-screen overflow-hidden bg-background text-foreground">
      <div className="mx-auto flex h-full max-w-[1800px] gap-4 px-3 py-3 sm:px-4 lg:px-5">
        <SessionSidebar
          sessions={workspace.sessions}
          activeSessionId={workspace.activeSessionId}
          loading={workspace.loadingSessions}
          onSelectSession={(id) => navigate(`/sessions/${id}`)}
          onNewSession={() => {
            workspace.resetWorkspace();
            navigate("/");
          }}
        />

        <ConversationView
          title={title}
          session={workspace.activeSession}
          messages={workspace.messages}
          draft={workspace.draft}
          draftAttachments={workspace.draftAttachments}
          verification={workspace.verification}
          verificationExpanded={workspace.verificationExpanded}
          runState={workspace.runState}
          onDraftChange={workspace.setDraft}
          onVerificationFieldChange={workspace.setVerificationField}
          onToggleVerification={workspace.toggleVerificationExpanded}
          onFilesSelected={workspace.addDraftFiles}
          onRemoveDraftAttachment={workspace.removeDraftAttachment}
          onSubmit={workspace.submitMessage}
          onToggleAudio={workspace.toggleAudio}
          audioEnabled={workspace.withAudio}
        />

        <ContextSidebar context={workspace.context} runState={workspace.runState} />
      </div>
    </div>
  );
}
