import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ConversationView } from "@/features/chat/components/conversation-view";
import { useAgentWorkspace } from "@/features/chat/hooks/use-agent-workspace";
import { ContextSidebar } from "@/features/context/components/context-sidebar";
import { SessionSidebar } from "@/features/session/components/session-sidebar";

function patientName(patient?: Record<string, unknown> | null) {
  if (!patient) return undefined;
  for (const key of ["name", "patient_name", "姓名"]) if (patient[key]) return String(patient[key]);
  return undefined;
}

export function WorkspacePage() {
  const navigate = useNavigate();
  const { sessionId } = useParams();
  const workspace = useAgentWorkspace(sessionId);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [contextCollapsed, setContextCollapsed] = useState(false);
  const title = useMemo(() => workspace.activeSession?.title || "患者端智能助手", [workspace.activeSession?.title]);

  return (
    <div className="h-[100dvh] overflow-hidden bg-white text-foreground">
      <div className="flex h-full min-w-0">
        <SessionSidebar sessions={workspace.sessions} activeSessionId={workspace.activeSessionId} loading={workspace.loadingSessions} mobileOpen={sidebarOpen} onCloseMobile={() => setSidebarOpen(false)} onSelectSession={(id) => navigate(`/sessions/${id}`)} onNewSession={() => { workspace.resetWorkspace(); navigate("/"); setSidebarOpen(false); }} />
        <ConversationView title={title} patientName={patientName(workspace.context?.patient)} session={workspace.activeSession} messages={workspace.messages} draft={workspace.draft} draftAttachments={workspace.draftAttachments} verification={workspace.verification} verificationExpanded={workspace.verificationExpanded} runState={workspace.runState} onDraftChange={workspace.setDraft} onVerificationFieldChange={workspace.setVerificationField} onToggleVerification={workspace.toggleVerificationExpanded} onFilesSelected={workspace.addDraftFiles} onRemoveDraftAttachment={workspace.removeDraftAttachment} onSubmit={workspace.submitMessage} onRetry={workspace.retryLastMessage} onToggleAudio={workspace.toggleAudio} audioEnabled={workspace.withAudio} onOpenSidebar={() => setSidebarOpen(true)} onOpenContext={() => setContextOpen(true)} />
        <ContextSidebar context={workspace.context} runState={workspace.runState} mobileOpen={contextOpen} collapsed={contextCollapsed} onCloseMobile={() => setContextOpen(false)} onToggleCollapsed={() => setContextCollapsed((current) => !current)} />
      </div>
    </div>
  );
}
