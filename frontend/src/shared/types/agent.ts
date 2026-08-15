export type SessionItem = {
  id: string;
  patient_id: string | null;
  title: string | null;
  status: string;
  last_message_preview: string | null;
  created_at: string;
  updated_at: string;
};

export type Attachment = {
  id: string;
  kind: string;
  status: string;
  session_id: string | null;
  patient_id: string | null;
  record_id: string | null;
  visit_id: string | null;
  image_id: string;
  file_name: string;
  mime_type: string;
  file_size: number;
  width: number | null;
  height: number | null;
  preview_url: string;
  download_url: string;
  source: string;
  created_at: string;
};

export type AudioAttachment = {
  file_name: string;
  file_path: string;
  download_url: string;
  transcript: string;
  voice: string;
  model: string;
  audio_format: string;
  sample_rate: number;
  file_size: number;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt?: string;
  attachments?: Attachment[];
  audio?: AudioAttachment | null;
  status?: "pending" | "streaming" | "done" | "error";
};

export type AgentTrace = {
  stage?: string;
  event: string;
  status: "started" | "completed" | "failed" | string;
  detail: string;
  error?: string;
  created_at?: string;
};

export type AgentInvokeResponse = {
  session_id: string;
  run_id?: string | null;
  final_answer: string;
  agent_trace: AgentTrace[];
  audio?: AudioAttachment | null;
  attachments: Attachment[];
};

export type SessionContext = {
  session: {
    id: string;
    patient_id: string | null;
    title: string | null;
    status: string;
    created_at: string;
    updated_at: string;
  };
  patient?: Record<string, unknown> | null;
  latest_agent_run?: { run_id?: string | null; final_answer?: string | null; created_at?: string | null } | null;
  attachments: Attachment[];
};

export type StoredMessage = {
  id: string;
  session_id: string;
  sequence_no: number;
  role: "user" | "assistant" | "system";
  message_type: string;
  content: string | null;
  payload?: Record<string, unknown> | null;
  created_at: string;
};

export type RunState = {
  mode: "idle" | "submitting" | "streaming" | "success" | "error";
  runId?: string | null;
  stages: AgentTrace[];
  error?: string | null;
};

export type DraftAttachment = {
  id: string;
  file: File;
  previewUrl: string;
};

export type VerificationFields = {
  verify_name: string;
  verify_phone: string;
  verify_id_card: string;
};
