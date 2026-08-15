import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { invokeAgent, streamAgent } from "@/shared/api/agent";
import { uploadAttachment } from "@/shared/api/attachments";
import { getSessionContext, getSessionMessages, listSessions } from "@/shared/api/sessions";
import type {
  AgentInvokeResponse,
  AudioAttachment,
  Attachment,
  ChatMessage,
  DraftAttachment,
  RunState,
  SessionContext,
  SessionItem,
  StoredMessage,
  VerificationFields,
} from "@/shared/types/agent";

function readAudioAttachment(value: unknown): AudioAttachment | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  if (!("download_url" in value) || !("file_name" in value)) {
    return null;
  }
  return value as AudioAttachment;
}

function mapStoredMessages(messages: StoredMessage[]): ChatMessage[] {
  return messages
    .filter((item) => item.message_type === "user_input" || item.message_type === "final_answer")
    .map((item) => ({
      id: item.id,
      role: item.message_type === "user_input" ? "user" : "assistant",
      content: item.content ?? "",
      attachments: Array.isArray(item.payload?.attachments) ? (item.payload.attachments as Attachment[]) : [],
      audio: readAudioAttachment(item.payload?.audio),
      createdAt: item.created_at,
      status: "done",
    }));
}

export function useAgentWorkspace(initialSessionId?: string) {
  const navigate = useNavigate();
  const streamingSessionIdRef = useRef<string | undefined>();
  const lastFailedRequestRef = useRef<Parameters<typeof streamAgent>[0] | undefined>();

  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [activeSessionId, setActiveSessionId] = useState<string | undefined>(initialSessionId);
  const [activeSession, setActiveSession] = useState<SessionItem | undefined>();
  const [context, setContext] = useState<SessionContext | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [verification, setVerification] = useState<VerificationFields>({
    verify_name: "",
    verify_phone: "",
    verify_id_card: "",
  });
  const [verificationExpanded, setVerificationExpanded] = useState(false);
  const [withAudio, setWithAudio] = useState(true);
  const [draftAttachments, setDraftAttachments] = useState<DraftAttachment[]>([]);
  const [runState, setRunState] = useState<RunState>({ mode: "idle", stages: [] });

  useEffect(() => {
    void refreshSessions();
  }, []);

  useEffect(() => {
    setActiveSessionId(initialSessionId);
  }, [initialSessionId]);

  useEffect(() => {
    if (!activeSessionId) {
      setActiveSession(undefined);
      setContext(undefined);
      setMessages([]);
      return;
    }
    if (
      streamingSessionIdRef.current === activeSessionId &&
      (runState.mode === "submitting" || runState.mode === "streaming")
    ) {
      return;
    }
    void hydrateSession(activeSessionId);
  }, [activeSessionId, runState.mode]);

  async function refreshSessions() {
    setLoadingSessions(true);
    try {
      const data = await listSessions();
      setSessions(data);
      if (activeSessionId) {
        setActiveSession(data.find((item) => item.id === activeSessionId));
      }
    } finally {
      setLoadingSessions(false);
    }
  }

  async function hydrateSession(sessionId: string) {
    const [sessionContext, storedMessages] = await Promise.all([getSessionContext(sessionId), getSessionMessages(sessionId)]);
    setContext(sessionContext);
    setMessages(mapStoredMessages(storedMessages));
    setActiveSession({
      id: sessionContext.session.id,
      patient_id: sessionContext.session.patient_id,
      title: sessionContext.session.title,
      status: sessionContext.session.status,
      created_at: sessionContext.session.created_at,
      updated_at: sessionContext.session.updated_at,
      last_message_preview: sessionContext.latest_agent_run?.final_answer ?? null,
    });
  }

  function addDraftFiles(files: FileList | null) {
    if (!files?.length) {
      return;
    }
    const next = Array.from(files).map((file) => ({
      id: crypto.randomUUID(),
      file,
      previewUrl: URL.createObjectURL(file),
    }));
    setDraftAttachments((current) => [...current, ...next]);
  }

  function removeDraftAttachment(id: string) {
    setDraftAttachments((current) => {
      const found = current.find((item) => item.id === id);
      if (found) {
        URL.revokeObjectURL(found.previewUrl);
      }
      return current.filter((item) => item.id !== id);
    });
  }

  async function submitMessage() {
    if (!draft.trim() && draftAttachments.length === 0) {
      return;
    }

    const pendingUserMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: draft.trim() || "查看上传图片",
      attachments: [],
      status: "done",
    };
    const pendingAssistantId = crypto.randomUUID();

    setMessages((current) => [
      ...current,
      pendingUserMessage,
      { id: pendingAssistantId, role: "assistant", content: "", status: "streaming" },
    ]);
    setRunState({ mode: "submitting", stages: [] });

    try {
      const uploadedAttachments = await Promise.all(draftAttachments.map((item) => uploadAttachment(item, activeSessionId)));
      pendingUserMessage.attachments = uploadedAttachments;
      setMessages((current) =>
        current.map((item) => (item.id === pendingUserMessage.id ? { ...item, attachments: uploadedAttachments } : item)),
      );

      const payload = {
        message: pendingUserMessage.content,
        session_id: activeSessionId,
        attachments: uploadedAttachments.map((item) => ({ id: item.id, kind: item.kind, image_id: item.image_id })),
        verify_name: verification.verify_name || undefined,
        verify_phone: verification.verify_phone || undefined,
        verify_id_card: verification.verify_id_card || undefined,
        with_audio: withAudio,
        metadata: {},
      };
      lastFailedRequestRef.current = payload;

      setDraft("");
      setDraftAttachments((current) => {
        current.forEach((item) => URL.revokeObjectURL(item.previewUrl));
        return [];
      });

      await executeAgent(payload, pendingAssistantId, pendingUserMessage.content);
    } catch (error) {
      const message = error instanceof Error ? error.message : "发送失败";
      streamingSessionIdRef.current = undefined;
      setRunState({ mode: "error", stages: [], error: message });
      setMessages((current) =>
        current.map((item) => (item.id === pendingAssistantId ? { ...item, content: message, status: "error" } : item)),
      );
    }
  }

  async function executeAgent(payload: Parameters<typeof streamAgent>[0], pendingAssistantId: string, fallbackTitle: string) {
    try {
      await streamAgent(payload, {
        onSessionCreated: (sessionId, runId) => {
          streamingSessionIdRef.current = sessionId;
          lastFailedRequestRef.current = { ...payload, session_id: sessionId };
          setActiveSessionId(sessionId);
          setActiveSession((current) => ({
            id: sessionId,
            patient_id: current?.patient_id ?? null,
            title: current?.title ?? fallbackTitle,
            status: "active",
            created_at: current?.created_at ?? new Date().toISOString(),
            updated_at: new Date().toISOString(),
            last_message_preview: null,
          }));
          setRunState((current) => ({ ...current, mode: "streaming", runId }));
          navigate(`/sessions/${sessionId}`, { replace: true });
        },
        onPhase: (trace) => {
          setRunState((current) => ({ ...current, mode: "streaming", stages: [...current.stages, trace] }));
        },
        onAnswerDelta: (delta) => {
          setRunState((current) => ({ ...current, mode: "streaming" }));
          setMessages((current) => current.map((item) => (item.id === pendingAssistantId ? { ...item, content: `${item.content}${delta}` } : item)));
        },
        onAnswerDone: (response) => finishAssistantMessage(pendingAssistantId, response),
      });
    } catch {
      const fallback = await invokeAgent(lastFailedRequestRef.current ?? payload);
      finishAssistantMessage(pendingAssistantId, fallback);
    }
  }

  async function retryLastMessage() {
    const payload = lastFailedRequestRef.current;
    if (!payload || runState.mode === "submitting" || runState.mode === "streaming") return;
    const pendingAssistantId = crypto.randomUUID();
    setMessages((current) => [...current, { id: pendingAssistantId, role: "assistant", content: "", status: "streaming" }]);
    setRunState({ mode: "submitting", stages: [] });
    try {
      await executeAgent(payload, pendingAssistantId, payload.message);
    } catch (error) {
      const message = error instanceof Error ? error.message : "发送失败";
      streamingSessionIdRef.current = undefined;
      setRunState({ mode: "error", stages: [], error: message });
      setMessages((current) => current.map((item) => (item.id === pendingAssistantId ? { ...item, content: message, status: "error" } : item)));
    }
  }

  function finishAssistantMessage(messageId: string, response: AgentInvokeResponse) {
    streamingSessionIdRef.current = undefined;
    lastFailedRequestRef.current = undefined;
    setRunState({
      mode: "success",
      runId: response.run_id,
      stages: response.agent_trace,
    });
    setMessages((current) =>
      current.map((item) =>
        item.id === messageId
          ? {
              ...item,
              content: response.final_answer,
              status: "done",
              attachments: response.attachments,
              audio: response.audio ?? null,
            }
          : item,
      ),
    );
    setActiveSessionId(response.session_id);
    navigate(`/sessions/${response.session_id}`, { replace: true });
    void Promise.all([refreshSessions(), hydrateSession(response.session_id)]);
  }

  function resetWorkspace() {
    streamingSessionIdRef.current = undefined;
    setActiveSessionId(undefined);
    setActiveSession(undefined);
    setContext(undefined);
    setMessages([]);
    setDraft("");
    setVerificationExpanded(false);
    setRunState({ mode: "idle", stages: [] });
  }

  function setVerificationField(field: keyof VerificationFields, value: string) {
    setVerification((current) => ({ ...current, [field]: value }));
  }

  return useMemo(
    () => ({
      sessions,
      loadingSessions,
      activeSessionId,
      activeSession,
      context,
      messages,
      draft,
      setDraft,
      verification,
      verificationExpanded,
      setVerificationField,
      toggleVerificationExpanded: () => setVerificationExpanded((current) => !current),
      withAudio,
      toggleAudio: () => setWithAudio((current) => !current),
      draftAttachments,
      addDraftFiles,
      removeDraftAttachment,
      submitMessage,
      retryLastMessage,
      runState,
      resetWorkspace,
    }),
    [
      sessions,
      loadingSessions,
      activeSessionId,
      activeSession,
      context,
      messages,
      draft,
      verification,
      verificationExpanded,
      withAudio,
      draftAttachments,
      runState,
    ],
  );
}
