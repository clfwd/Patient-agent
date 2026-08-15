import { Bot, FileImage } from "lucide-react";

import { AgentStatusStrip } from "@/features/agent/components/agent-status-strip";
import { MarkdownAnswer } from "@/features/chat/components/markdown-answer";
import { buildUrl } from "@/shared/api/http";
import type { ChatMessage, RunState } from "@/shared/types/agent";

type MessageListProps = {
  messages: ChatMessage[];
  runState: RunState;
  onRetry?: () => void;
};

export function MessageList({ messages, runState, onRetry }: MessageListProps) {
  const latestAssistantIndex = [...messages].map((message) => message.role).lastIndexOf("assistant");

  return (
    <div className="mx-auto flex w-full max-w-[900px] flex-col gap-7 px-5 pb-6 pt-7 sm:px-8">
      {messages.map((message, index) => {
        const isLatestAssistant = message.role === "assistant" && index === latestAssistantIndex;
        return (
          <article key={message.id} className={message.role === "user" ? "ml-auto max-w-[72%]" : "max-w-full"}>
            {message.role === "assistant" ? (
              <div className="flex gap-3 sm:gap-4">
                <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[#eef3f7] text-accent"><Bot className="h-4 w-4" /></div>
                <div className="min-w-0 flex-1">
                  {isLatestAssistant && (message.status !== "done" || runState.mode === "success" || runState.mode === "error") ? <AgentStatusStrip runState={runState} onRetry={onRetry} /> : null}
                  {message.content ? <MarkdownAnswer content={message.content} /> : message.status === "streaming" ? <p className="text-sm text-muted">正在准备回复…</p> : null}
                  {message.audio ? (
                    <div className="mt-5 max-w-md border-l-2 border-line pl-3">
                      <div className="mb-2 text-xs text-muted">语音回复</div>
                      <audio className="w-full" controls preload="none" src={message.audio.download_url.startsWith("http") ? message.audio.download_url : buildUrl(message.audio.download_url)} />
                      <a className="mt-2 inline-flex text-xs text-muted underline underline-offset-4 hover:text-foreground" href={message.audio.download_url.startsWith("http") ? message.audio.download_url : buildUrl(message.audio.download_url)} target="_blank" rel="noreferrer">下载音频</a>
                    </div>
                  ) : null}
                </div>
              </div>
            ) : (
              <div className="rounded-2xl bg-[#f1f2f3] px-4 py-3 text-[15px] leading-7 text-foreground">
                {message.attachments?.length ? (
                  <div className="mb-3 flex flex-wrap gap-2">
                    {message.attachments.map((attachment) => (
                      <div key={attachment.id} className="relative">
                        <img alt={attachment.file_name} className="h-16 w-16 rounded-lg object-cover" src={attachment.preview_url.startsWith("http") ? attachment.preview_url : buildUrl(attachment.preview_url)} />
                        <FileImage className="absolute bottom-1 right-1 h-3.5 w-3.5 rounded bg-white/85 p-0.5 text-muted" />
                      </div>
                    ))}
                  </div>
                ) : null}
                <div className="whitespace-pre-wrap">{message.content}</div>
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
