import { requestJson } from "@/shared/api/http";
import type { SessionContext, SessionItem, StoredMessage } from "@/shared/types/agent";

export function listSessions() {
  return requestJson<SessionItem[]>("/api/v1/chat/sessions");
}

export function getSessionContext(sessionId: string) {
  return requestJson<SessionContext>(`/api/v1/chat/sessions/${sessionId}/context`);
}

export function getSessionMessages(sessionId: string) {
  return requestJson<StoredMessage[]>(`/api/v1/chat/sessions/${sessionId}/messages`);
}
