import { buildUrl } from "@/shared/api/http";
import type { Attachment, DraftAttachment } from "@/shared/types/agent";

export async function uploadAttachment(draft: DraftAttachment, sessionId?: string) {
  const formData = new FormData();
  formData.append("file", draft.file);
  if (sessionId) {
    formData.append("session_id", sessionId);
  }

  const response = await fetch(buildUrl("/api/v1/chat/attachments/upload"), {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error("图片上传失败");
  }
  return response.json() as Promise<Attachment>;
}
