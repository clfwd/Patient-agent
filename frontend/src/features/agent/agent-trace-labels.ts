import type { AgentTrace } from "@/shared/types/agent";

const STAGE_LABELS: Record<string, string> = {
  preflight: "身份与上下文",
  tool_calling: "检索相关信息",
  postprocess: "生成回复",
  graph_preflight: "准备会话上下文",
  graph_skill_selector: "识别咨询场景",
  graph_memory_bootstrap: "加载患者背景",
  graph_planner: "规划处理步骤",
  graph_dispatcher: "调度所需能力",
  graph_memory_agent: "检索既往对话信息",
  graph_patient_data_agent: "查询患者资料",
  graph_image_analysis_agent: "分析上传图片",
  graph_medical_knowledge_agent: "检索医学资料",
  graph_join: "汇总相关信息",
  graph_gap_checker: "检查信息完整性",
  graph_composer: "生成回复",
  graph_postprocess: "整理回复结果",
};

export function traceStageLabel(trace: AgentTrace) {
  const stage = trace.stage || trace.event;
  return STAGE_LABELS[stage] || "处理你的问题";
}

export function traceStatusLabel(status: string) {
  if (status === "started") {
    return "开始";
  }
  if (status === "completed") {
    return "完成";
  }
  if (status === "failed") {
    return "失败";
  }
  if (status === "constraint") {
    return "约束";
  }
  return status;
}
