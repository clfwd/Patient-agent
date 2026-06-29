"""Structured schemas for bounded graph planning and worker evidence."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, conint, validator


class PlannedTask(BaseModel):
    task_id: str = Field(..., description="Stable task identifier unique within one graph run.")
    agent: str = Field(..., description="Graph worker node selected from the server capability registry.")
    goal: str = Field(..., description="Concrete worker goal; this is intent, not a tool call.")
    status: str = Field("pending", description="Task lifecycle status managed by dispatcher and join.")
    depends_on: List[str] = Field(default_factory=list, description="Task ids that must finish before this task is ready.")
    result_key: str = Field(..., description="State/result key where the worker result should be summarized.")
    priority: conint(ge=0, le=100) = Field(50, description="Higher priority tasks dispatch first.")
    required: bool = Field(True, description="Whether failure should trigger retry/replan pressure.")
    dedupe_key: str = Field(..., description="Semantic key used to prevent duplicate proposed tasks.")
    created_by: str = Field("graph_planner", description="Planner or replanner component that created the task.")
    parent_task_id: Optional[str] = Field(None, description="Parent task id when proposed during replanning.")
    retry_count: int = Field(0, description="Retry attempts already used.")
    max_retries: int = Field(1, description="Maximum retry attempts for required tasks.")
    timeout_seconds: int = Field(20, description="Soft execution budget for the worker.")
    reason: str = Field("", description="Why this task is needed.")
    allowed_tools: List[str] = Field(default_factory=list, description="Planner-requested tools; server policy must intersect this list.")
    expected_evidence: List[str] = Field(default_factory=list, description="Evidence the worker should try to produce.")
    max_tool_steps: int = Field(1, description="Planner-requested ReAct step budget before server caps are applied.")
    effective_allowed_tools: List[str] = Field(default_factory=list, description="Server-validated tool allowlist actually injected into the worker.")
    effective_max_tool_steps: int = Field(1, description="Server-capped ReAct step budget actually used by the worker.")

    @validator("dedupe_key", "task_id", "agent", "result_key")
    def _not_blank(cls, value):
        if not str(value or "").strip():
            raise ValueError("field cannot be blank")
        return value


class PlannerOutput(BaseModel):
    tasks: List[PlannedTask] = Field(default_factory=list, description="Initial task board.")
    risk_flags: List[str] = Field(default_factory=list, description="Risk keywords or clinical risk hints.")
    conversation_context_summary: Dict[str, Any] = Field(default_factory=dict, description="Short-term conversation summary for reference resolution.")
    planning_notes: str = Field("", description="Brief planner rationale for trace/debug only.")


class WorkerEvidence(BaseModel):
    evidence_id: str = Field(..., description="Unique evidence id within the graph run.")
    task_id: str = Field(..., description="Task that produced this evidence.")
    agent_name: str = Field(..., description="Worker or agent that produced this evidence.")
    source_type: str = Field(..., description="patient_data, image_analysis, medical_knowledge, or memory.")
    source_id: Optional[str] = Field(None, description="Record, image, chunk, memory, or tool identifier.")
    source_title: Optional[str] = Field(None, description="Human-readable source label.")
    content_summary: Any = Field(..., description="Evidence summary consumed by Composer.")
    raw_excerpt: Optional[Any] = Field(None, description="Short raw excerpt when available.")
    time: Optional[str] = Field(None, description="Source time if available.")
    confidence: float = Field(0.5, description="Worker confidence from 0 to 1.")
    patient_specific: bool = Field(False, description="True when this is a fact about the verified patient.")
    medical_knowledge: bool = Field(False, description="True when this evidence is general medical knowledge.")
    limitations: List[str] = Field(default_factory=list, description="Known evidence limits and uncertainty.")


class AnswerConstraints(BaseModel):
    answer_constraints: List[str] = Field(default_factory=list, description="Rules Composer must follow.")
    forbidden_claims: List[str] = Field(default_factory=list, description="Claims Composer must not make.")
    must_include_disclaimer: bool = Field(False, description="Whether Composer must include a medical disclaimer.")
    must_recommend_emergency_care: bool = Field(False, description="Whether Composer must recommend urgent/emergency care.")


class SafetySignals(AnswerConstraints):
    safety_level: Literal["normal", "caution", "urgent"] = Field("normal", description="Medical safety level for the final answer.")
    urgent_flags: List[str] = Field(default_factory=list, description="Urgent symptoms or risk patterns detected.")


class ReplanDecision(SafetySignals):
    decision: Literal["finish", "continue", "force_finish"] = Field(..., description="Whether to finish, dispatch more tasks, or degrade because budgets are exhausted.")
    finish_reason: Literal[
        "evidence_sufficient",
        "max_rounds_reached",
        "max_tasks_reached",
        "unrecoverable_required_task_failed",
        "degraded_answer_allowed",
    ] = Field("evidence_sufficient", description="Why the graph is allowed or forced to enter Composer.")
    missing_evidence: List[str] = Field(default_factory=list, description="Evidence gaps relative to the user question.")
    proposed_tasks: List[PlannedTask] = Field(default_factory=list, description="Incremental tasks proposed by Replanner.")
    stop_reason: str = Field("", description="Human-readable stopping or continuation reason.")
    confidence: float = Field(0.5, description="Confidence in the replan decision.")
