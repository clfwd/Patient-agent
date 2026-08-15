import { Check, ChevronRight, PanelRightClose, X } from "lucide-react";

import type { RunState, SessionContext } from "@/shared/types/agent";

type ContextSidebarProps = { context?: SessionContext; runState: RunState; mobileOpen: boolean; collapsed: boolean; onCloseMobile: () => void; onToggleCollapsed: () => void };

function valueOf(patient: Record<string, unknown> | null | undefined, keys: string[]) {
  if (!patient) return undefined;
  for (const key of keys) if (patient[key] !== undefined && patient[key] !== null) return String(patient[key]);
  return undefined;
}

function mask(value?: string) {
  if (!value) return "—";
  if (value.length <= 4) return value;
  return `${value.slice(0, 3)}****${value.slice(-4)}`;
}

export function ContextSidebar({ context, runState, mobileOpen, collapsed, onCloseMobile, onToggleCollapsed }: ContextSidebarProps) {
  const patient = context?.patient;
  const patientName = valueOf(patient, ["name", "patient_name", "姓名"]);
  const patientNo = valueOf(patient, ["patient_no", "patientNo", "编号"]);
  const gender = valueOf(patient, ["gender", "性别"]);
  const age = valueOf(patient, ["age", "年龄"]);
  const phone = valueOf(patient, ["phone", "mobile", "手机号"]);
  const runLabel = runState.mode === "error" ? "执行遇到问题" : runState.mode === "submitting" || runState.mode === "streaming" ? "正在分析" : runState.mode === "success" ? "已完成" : "等待提问";
  const content = <><div className="flex items-center justify-between border-b border-line px-4 py-4"><div><p className="text-[15px] font-semibold text-foreground">患者信息</p><p className="mt-0.5 text-xs text-muted">当前会话辅助信息</p></div><button aria-label="关闭患者信息" className="rounded-md p-1.5 text-muted hover:bg-black/[0.04] xl:hidden" onClick={onCloseMobile} type="button"><X className="h-4 w-4" /></button><button aria-label="收起患者信息" className="hidden rounded-md p-1.5 text-muted hover:bg-black/[0.04] xl:inline-flex" onClick={onToggleCollapsed} type="button"><PanelRightClose className="h-4 w-4" /></button></div><div className="space-y-7 px-4 py-5"><section><p className="text-base font-semibold text-foreground">{patientName || "尚未识别患者"}</p><p className="mt-1 text-sm text-muted">{patientNo || "发送问题并完成核验后显示"}</p>{patientName ? <p className="mt-2 text-sm text-muted">{[gender, age ? `${age} 岁` : undefined].filter(Boolean).join(" · ") || "基本信息暂缺"}</p> : null}{phone ? <p className="mt-3 text-xs text-muted">联系方式：{mask(phone)}</p> : null}</section><section className="border-t border-line pt-5"><p className="text-xs font-medium text-muted">当前会话</p><p className="mt-2 line-clamp-2 text-sm leading-6 text-foreground">{context?.session.title || "未命名会话"}</p><p className="mt-2 text-sm text-muted">状态：{context?.session.status || "new"}</p><p className="mt-1 text-sm text-muted">附件：{context?.attachments.length ?? 0}</p></section><section className="border-t border-line pt-5"><p className="text-xs font-medium text-muted">Agent</p><div className="mt-2 flex items-center gap-2 text-sm text-foreground"><Check className={`h-4 w-4 ${runState.mode === "error" ? "text-[#b4533c]" : "text-[#4f6f62]"}`} />{runLabel}</div></section></div></>;
  return <>{collapsed ? <button aria-label="展开患者信息" className="hidden h-full w-9 shrink-0 border-l border-line bg-[#fafafa] text-muted hover:bg-[#f5f5f5] xl:inline-flex xl:items-center xl:justify-center" onClick={onToggleCollapsed} type="button"><ChevronRight className="h-4 w-4" /></button> : <aside className="hidden h-full w-[288px] shrink-0 flex-col border-l border-line bg-[#fafafa] xl:flex">{content}</aside>}{mobileOpen ? <div className="fixed inset-0 z-40 xl:hidden"><button aria-label="关闭患者信息" className="absolute inset-0 bg-black/20" onClick={onCloseMobile} type="button" /><aside className="absolute right-0 flex h-full w-[300px] max-w-[86vw] flex-col bg-[#fafafa] shadow-xl">{content}</aside></div> : null}</>;
}
