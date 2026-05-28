import { ChevronDown, ImagePlus, Send, ShieldCheck } from "lucide-react";
import type { ChangeEvent, FormEvent } from "react";

import { Button } from "@/shared/ui/button";
import { Textarea } from "@/shared/ui/textarea";
import type { DraftAttachment, VerificationFields } from "@/shared/types/agent";

type ComposerProps = {
  draft: string;
  draftAttachments: DraftAttachment[];
  verification: VerificationFields;
  verificationExpanded: boolean;
  audioEnabled: boolean;
  disabled: boolean;
  onDraftChange: (value: string) => void;
  onVerificationFieldChange: (field: keyof VerificationFields, value: string) => void;
  onToggleVerification: () => void;
  onFilesSelected: (files: FileList | null) => void;
  onRemoveDraftAttachment: (id: string) => void;
  onSubmit: () => void;
  onToggleAudio: () => void;
};

export function Composer({
  draft,
  draftAttachments,
  verification,
  verificationExpanded,
  audioEnabled,
  disabled,
  onDraftChange,
  onVerificationFieldChange,
  onToggleVerification,
  onFilesSelected,
  onRemoveDraftAttachment,
  onSubmit,
  onToggleAudio,
}: ComposerProps) {
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!draft.trim() && draftAttachments.length === 0) {
      return;
    }
    onSubmit();
  };

  const handleFiles = (event: ChangeEvent<HTMLInputElement>) => {
    onFilesSelected(event.target.files);
    event.target.value = "";
  };

  const canSubmit = !disabled && (draft.trim().length > 0 || draftAttachments.length > 0);

  return (
    <form className="glass-panel mt-6 p-4" onSubmit={handleSubmit}>
      {draftAttachments.length ? (
        <div className="mb-3 flex flex-wrap gap-3">
          {draftAttachments.map((attachment) => (
            <div key={attachment.id} className="group relative">
              <img alt={attachment.file.name} className="h-20 w-20 rounded-2xl object-cover" src={attachment.previewUrl} />
              <button
                className="absolute right-2 top-2 rounded-full bg-black/70 px-2 py-1 text-xs text-white opacity-0 transition group-hover:opacity-100"
                onClick={() => onRemoveDraftAttachment(attachment.id)}
                type="button"
              >
                删除
              </button>
            </div>
          ))}
        </div>
      ) : null}

      <div className="mb-3 rounded-[24px] border border-line/80 bg-white/60">
        <button
          className="flex w-full items-center justify-between px-4 py-3 text-left"
          onClick={onToggleVerification}
          type="button"
        >
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-foreground" />
            <div>
              <div className="text-sm font-medium text-foreground">身份核验</div>
              <div className="text-xs text-muted">敏感病历、复诊、图片分析前建议先填写。</div>
            </div>
          </div>
          <ChevronDown className={`h-4 w-4 text-muted transition ${verificationExpanded ? "rotate-180" : ""}`} />
        </button>

        {verificationExpanded ? (
          <div className="grid gap-3 border-t border-line/80 px-4 py-4 md:grid-cols-3">
            <input
              className="rounded-2xl border border-line bg-transparent px-3 py-3 text-sm outline-none placeholder:text-muted focus:border-foreground/20"
              placeholder="姓名"
              value={verification.verify_name}
              onChange={(event) => onVerificationFieldChange("verify_name", event.target.value)}
            />
            <input
              className="rounded-2xl border border-line bg-transparent px-3 py-3 text-sm outline-none placeholder:text-muted focus:border-foreground/20"
              placeholder="手机号"
              value={verification.verify_phone}
              onChange={(event) => onVerificationFieldChange("verify_phone", event.target.value)}
            />
            <input
              className="rounded-2xl border border-line bg-transparent px-3 py-3 text-sm outline-none placeholder:text-muted focus:border-foreground/20"
              placeholder="身份证号"
              value={verification.verify_id_card}
              onChange={(event) => onVerificationFieldChange("verify_id_card", event.target.value)}
            />
          </div>
        ) : null}
      </div>

      <Textarea
        placeholder="输入你的问题，例如：帮我总结最近一次复诊情况。"
        value={draft}
        onChange={(event) => onDraftChange(event.target.value)}
      />

      <div className="mt-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-full bg-warm px-4 py-2 text-sm text-foreground">
            <ImagePlus className="h-4 w-4" />
            添加图片
            <input accept="image/*" className="hidden" multiple type="file" onChange={handleFiles} />
          </label>
          <Button type="button" variant="ghost" onClick={onToggleAudio}>
            语音播报: {audioEnabled ? "开" : "关"}
          </Button>
        </div>

        <Button className="gap-2" disabled={!canSubmit} type="submit">
          <Send className="h-4 w-4" />
          发送
        </Button>
      </div>
    </form>
  );
}
