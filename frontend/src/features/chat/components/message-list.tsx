import { useEffect, useRef } from "react";

import { buildUrl } from "@/shared/api/http";
import type { ChatMessage } from "@/shared/types/agent";

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  return (
    <div className="flex flex-col gap-5 pb-2">
      {messages.map((message) => (
        <div key={message.id} className={message.role === "user" ? "ml-auto max-w-[80%]" : "mr-auto max-w-[85%]"}>
          <div className={`rounded-[28px] px-5 py-4 ${message.role === "user" ? "bg-foreground text-white" : "bg-white/80 text-foreground"}`}>
            {message.attachments?.length ? (
              <div className="mb-3 flex flex-wrap gap-3">
                {message.attachments.map((attachment) => (
                  <img
                    key={attachment.id}
                    alt={attachment.file_name}
                    className="h-20 w-20 rounded-2xl object-cover"
                    src={attachment.preview_url.startsWith("http") ? attachment.preview_url : buildUrl(attachment.preview_url)}
                  />
                ))}
              </div>
            ) : null}
            <div className="whitespace-pre-wrap text-[15px] leading-7">{message.content}</div>
            {message.audio ? (
              <div className="mt-4 rounded-2xl border border-line/80 bg-black/[0.03] px-3 py-3">
                <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted">Audio Reply</div>
                <audio
                  className="w-full"
                  controls
                  preload="none"
                  src={message.audio.download_url.startsWith("http") ? message.audio.download_url : buildUrl(message.audio.download_url)}
                />
                <a
                  className="mt-2 inline-flex text-sm text-muted underline-offset-4 hover:text-foreground hover:underline"
                  href={message.audio.download_url.startsWith("http") ? message.audio.download_url : buildUrl(message.audio.download_url)}
                  target="_blank"
                  rel="noreferrer"
                >
                  下载音频
                </a>
              </div>
            ) : null}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
