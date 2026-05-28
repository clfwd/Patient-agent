import { buildUrl, requestJson } from "@/shared/api/http";
import type { AgentInvokeResponse, AgentTrace } from "@/shared/types/agent";

type InvokePayload = {
  message: string;
  session_id?: string;
  attachments?: Array<{ id: string; kind: string; image_id: string }>;
  verify_name?: string;
  verify_phone?: string;
  verify_id_card?: string;
  with_audio: boolean;
  metadata: Record<string, unknown>;
};

export async function invokeAgent(payload: InvokePayload) {
  return requestJson<AgentInvokeResponse>("/api/v1/agent/invoke", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function streamAgent(
  payload: InvokePayload,
  handlers: {
    onSessionCreated: (sessionId: string, runId?: string | null) => void;
    onPhase: (trace: AgentTrace) => void;
    onAnswerDelta: (delta: string) => void;
    onAnswerDone: (response: AgentInvokeResponse) => void;
  },
) {
  const response = await fetch(buildUrl("/api/v1/agent/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    throw new Error("流式连接失败");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let completed = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const lines = frame.split("\n").filter(Boolean);
      let eventName = "message";
      let data = "";

      for (const line of lines) {
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        }
        if (line.startsWith("data:")) {
          data += line.slice(5).trim();
        }
      }

      if (!data) {
        continue;
      }

      const parsed = JSON.parse(data) as
        | AgentInvokeResponse
        | AgentTrace
        | { delta?: string; session_id?: string; run_id?: string | null; message?: string };

      if (eventName === "session.created") {
        const event = parsed as { session_id?: string; run_id?: string | null };
        if (event.session_id) {
          handlers.onSessionCreated(event.session_id, event.run_id);
        }
      } else if (eventName === "agent.phase") {
        handlers.onPhase(parsed as AgentTrace);
      } else if (eventName === "answer.delta") {
        handlers.onAnswerDelta(String((parsed as { delta?: string }).delta ?? ""));
      } else if (eventName === "answer.done") {
        completed = true;
        handlers.onAnswerDone(parsed as AgentInvokeResponse);
      } else if (eventName === "agent.error") {
        throw new Error(String((parsed as { message?: string }).message ?? "Agent 执行失败"));
      }
    }
  }

  if (!completed) {
    throw new Error("流式响应提前结束");
  }
}
