"""State helpers for the patient agent graph."""

from typing import Any, Dict, List, Optional, TypedDict
from typing_extensions import Annotated


def merge_list(left, right):
    left_items = list(left or [])
    right_items = list(right or [])
    if not right_items:
        return left_items
    if right_items[: len(left_items)] == left_items:
        return right_items
    return left_items + right_items


def merge_unique_list(left, right):
    result = []
    for item in list(left or []) + list(right or []):
        if item not in result:
            result.append(item)
    return result


def merge_dict(left, right):
    result = dict(left or {})
    result.update(dict(right or {}))
    return result


class AgentStep(TypedDict, total=False):
    name: str
    status: str
    detail: str
    tool_name: str


class AgentToolCall(TypedDict, total=False):
    tool_name: str
    arguments: Dict[str, Any]
    ok: bool
    result: Dict[str, Any]
    error: Optional[str]


class AgentTraceEvent(TypedDict, total=False):
    stage: str
    event: str
    status: str
    detail: str
    tool_name: str
    arguments: Dict[str, Any]
    error: Optional[str]
    created_at: Any


class AgentTask(TypedDict, total=False):
    task_id: str
    agent: str
    goal: str
    status: str
    depends_on: List[str]
    result_key: str
    priority: int
    required: bool
    dedupe_key: str
    created_by: str
    parent_task_id: Optional[str]
    retry_count: int
    max_retries: int
    timeout_seconds: int
    reason: str
    allowed_tools: List[str]
    expected_evidence: List[str]
    max_tool_steps: int
    effective_allowed_tools: List[str]
    effective_max_tool_steps: int


class AgentState(TypedDict, total=False):
    message: str
    session_id: Optional[str]
    session_patient_id: Optional[str]
    patient_id: Optional[str]
    patient_no: Optional[str]
    visit_no: Optional[str]
    verify_name: Optional[str]
    verify_phone: Optional[str]
    verify_id_card: Optional[str]
    image_id: Optional[str]
    attachments: List[Dict[str, Any]]
    with_audio: bool
    metadata: Dict[str, Any]
    conversation_history: List[Dict[str, str]]
    conversation_context_summary: Optional[Dict[str, Any]]
    message_recorder: Any
    plan: Annotated[List[str], merge_unique_list]
    task_board: List[AgentTask]
    current_task: Optional[AgentTask]
    dispatched_tasks: List[AgentTask]
    task_results: Annotated[Dict[str, Any], merge_dict]
    worker_events: Annotated[List[Dict[str, Any]], merge_list]
    proposed_tasks: Annotated[List[AgentTask], merge_list]
    suggested_followups: Annotated[List[Dict[str, Any]], merge_list]
    evidence_items: Annotated[List[Dict[str, Any]], merge_list]
    risk_flags: List[str]
    safety_level: Optional[str]
    urgent_flags: List[str]
    answer_constraints: List[str]
    forbidden_claims: List[str]
    finish_reason: Optional[str]
    join_summary: Dict[str, Any]
    need_more_tasks: bool
    dispatch_round: int
    max_dispatch_rounds: int
    max_tasks: int
    max_new_tasks_per_round: int
    max_parallel_tasks: int
    steps: List[AgentStep]
    tool_calls: Annotated[List[AgentToolCall], merge_list]
    agent_trace: Annotated[List[AgentTraceEvent], merge_list]
    identity_verification: Optional[Dict[str, Any]]
    verified_patient: Optional[Dict[str, Any]]
    allowed_patient_id: Optional[str]
    image_context: Optional[Dict[str, Any]]
    patient_profile: Optional[Dict[str, Any]]
    visit_search_result: Optional[Dict[str, Any]]
    record_search_result: Optional[Dict[str, Any]]
    image_analysis: Optional[Dict[str, Any]]
    knowledge_hits: List[Dict[str, Any]]
    knowledge_retrieval_mode: Optional[str]
    knowledge_sources_text: Optional[str]
    planner_mode: Optional[str]
    planner_output_mode: Optional[str]
    replanner_mode: Optional[str]
    replanner_output_mode: Optional[str]
    tool_calling_mode: Optional[str]
    run_id: Optional[str]
    final_answer: Optional[str]
    audio: Optional[Dict[str, Any]]
    attachments_result: List[Dict[str, Any]]
    errors: Annotated[List[str], merge_list]
