"""State helpers for the patient agent graph."""

from typing import Any, Dict, List, Optional, TypedDict


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
    message_recorder: Any
    plan: List[str]
    task_board: List[AgentTask]
    current_task: Optional[AgentTask]
    task_results: Dict[str, Any]
    worker_events: List[Dict[str, Any]]
    proposed_tasks: List[AgentTask]
    evidence_items: List[Dict[str, Any]]
    risk_flags: List[str]
    join_summary: Dict[str, Any]
    need_more_tasks: bool
    dispatch_round: int
    max_dispatch_rounds: int
    max_tasks: int
    max_new_tasks_per_round: int
    steps: List[AgentStep]
    tool_calls: List[AgentToolCall]
    agent_trace: List[AgentTraceEvent]
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
    tool_calling_mode: Optional[str]
    run_id: Optional[str]
    final_answer: Optional[str]
    audio: Optional[Dict[str, Any]]
    attachments_result: List[Dict[str, Any]]
    errors: List[str]
