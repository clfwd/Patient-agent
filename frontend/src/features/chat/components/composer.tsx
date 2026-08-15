import { ChevronDown, ImagePlus, Send, ShieldCheck, X } from "lucide-react";
import { useEffect, useRef } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { Button } from "@/shared/ui/button";
import { Textarea } from "@/shared/ui/textarea";
import type { DraftAttachment, VerificationFields } from "@/shared/types/agent";

type ComposerProps = {
  draft: string; draftAttachments: DraftAttachment[]; verification: VerificationFields; verificationExpanded: boolean; audioEnabled: boolean; disabled: boolean;
  onDraftChange: (value: string) => void; onVerificationFieldChange: (field: keyof VerificationFields, value: string) => void; onToggleVerification: () => void;
  onFilesSelected: (files: FileList | null) => void; onRemoveDraftAttachment: (id: string) => void; onSubmit: () => void; onToggleAudio: () => void;
};

export function Composer({ draft, draftAttachments, verification, verificationExpanded, audioEnabled, disabled, onDraftChange, onVerificationFieldChange, onToggleVerification, onFilesSelected, onRemoveDraftAttachment, onSubmit, onToggleAudio }: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const hasVerification = Boolean(verification.verify_name || verification.verify_phone || verification.verify_id_card);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 208)}px`;
  }, [draft]);

  const handleSubmit = (event: FormEvent) => { event.preventDefault(); if (draft.trim() || draftAttachments.length) onSubmit(); };
  const handleFiles = (event: ChangeEvent<HTMLInputElement>) => { onFilesSelected(event.target.files); event.target.value = ""; };
  const canSubmit = !disabled && (draft.trim().length > 0 || draftAttachments.length > 0);

  return (
    <form className="rounded-2xl border border-line bg-white px-3 py-2.5 transition focus-within:border-foreground/20" onSubmit={handleSubmit}>
      {draftAttachments.length ? <div className="mb-2 flex flex-wrap gap-2">{draftAttachments.map((attachment) => <div key={attachment.id} className="group relative"><img alt={attachment.file.name} className="h-16 w-16 rounded-lg object-cover" src={attachment.previewUrl} /><button aria-label={`移除 ${attachment.file.name}`} className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-foreground text-white opacity-0 transition group-hover:opacity-100 focus:opacity-100" onClick={() => onRemoveDraftAttachment(attachment.id)} type="button"><X className="h-3 w-3" /></button></div>)}</div> : null}
      <button className="mb-1 flex w-full items-center gap-2 rounded-lg px-1 py-1.5 text-left text-xs text-muted hover:bg-black/[0.02]" onClick={onToggleVerification} type="button">
        <ShieldCheck className={`h-4 w-4 ${hasVerification ? "text-[#4f6f62]" : "text-accent"}`} />
        <span className="flex-1">{hasVerification ? "身份核验信息已填写" : "访问敏感病历或进行图片分析前需要身份核验"}</span>
        <span className="font-medium text-foreground">{verificationExpanded ? "收起" : hasVerification ? "查看" : "去核验"}</span><ChevronDown className={`h-3.5 w-3.5 transition ${verificationExpanded ? "rotate-180" : ""}`} />
      </button>
      {verificationExpanded ? <div className="mb-2 grid gap-2 border-b border-line pb-3 pt-1 sm:grid-cols-3"><input className="h-9 rounded-md bg-surface px-2.5 text-sm outline-none placeholder:text-muted focus:ring-1 focus:ring-foreground/15" placeholder="姓名" value={verification.verify_name} onChange={(event) => onVerificationFieldChange("verify_name", event.target.value)} /><input className="h-9 rounded-md bg-surface px-2.5 text-sm outline-none placeholder:text-muted focus:ring-1 focus:ring-foreground/15" placeholder="手机号" value={verification.verify_phone} onChange={(event) => onVerificationFieldChange("verify_phone", event.target.value)} /><input className="h-9 rounded-md bg-surface px-2.5 text-sm outline-none placeholder:text-muted focus:ring-1 focus:ring-foreground/15" placeholder="身份证号" value={verification.verify_id_card} onChange={(event) => onVerificationFieldChange("verify_id_card", event.target.value)} /></div> : null}
      <Textarea ref={textareaRef} placeholder="输入你的问题…" value={draft} onChange={(event) => onDraftChange(event.target.value)} />
      <div className="mt-1.5 flex items-center justify-between gap-2"><div className="flex items-center gap-1"><label className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md px-2 text-sm text-muted transition hover:bg-black/[0.04] hover:text-foreground"><ImagePlus className="h-4 w-4" /><span className="hidden sm:inline">添加图片</span><input accept="image/*" className="hidden" multiple type="file" onChange={handleFiles} /></label><button className="h-8 rounded-md px-2 text-xs text-muted transition hover:bg-black/[0.04] hover:text-foreground" onClick={onToggleAudio} type="button">语音：{audioEnabled ? "开" : "关"}</button></div><Button aria-label="发送消息" className="h-8 w-8 rounded-lg p-0" disabled={!canSubmit} type="submit"><Send className="h-4 w-4" /></Button></div>
    </form>
  );
}
