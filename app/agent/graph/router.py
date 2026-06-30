"""Task-board planner and dispatcher helpers for the LangGraph agent."""

from langgraph.types import Send

from app.tool_routing import IMAGE_KEYWORDS, RECORD_KEYWORDS, VISIT_KEYWORDS

from .capabilities import normalize_planned_tasks
from .state import (
    GRAPH_COMPOSER,
    GRAPH_IMAGE_ANALYSIS,
    GRAPH_JOIN,
    GRAPH_MEDICAL_KNOWLEDGE,
    GRAPH_MEDICAL_KNOWLEDGE_AGENT,
    GRAPH_MEMORY,
    GRAPH_PATIENT_DATA,
)


KNOWLEDGE_KEYWORDS = (
    "what is",
    "meaning of",
    "blood sugar",
    "blood pressure",
    "fever",
    "cough",
    "glucose",
    "hypertension",
    "血糖",
    "血压",
    "发热",
    "咳嗽",
    "指标",
    "检查",
)
PATIENT_DATA_KEYWORDS = (
    "我的",
    "患者",
    "资料",
    "个人信息",
    "病历",
    "病例",
    "病史",
    "诊断",
    "就诊",
    "复诊",
    "最近",
    "最新",
    "my ",
    "profile",
    "record",
    "visit",
    "diagnosis",
)
IMAGE_REFERENCE_KEYWORDS = (
    "图片",
    "图像",
    "影像",
    "报告",
    "这张图",
    "这个图",
    "图里",
    "图片里",
    "this image",
    "this photo",
    "this picture",
    "this report",
    "uploaded image",
    "uploaded report",
    "lab report",
    "x-ray",
    "scan",
)
RISK_KEYWORDS = (
    "胸痛",
    "chest pain",
    "呼吸困难",
    "昏迷",
    "大出血",
    "自杀",
    "休克",
    "severe chest pain",
    "shortness of breath",
    "suicide",
    "unconscious",
)


def _message(state):
    return (state.get("message") or "").lower()


def _contains_any(message, keywords):
    return any(keyword in message for keyword in keywords)


def _make_task(
    agent,
    task_type,
    goal,
    result_key,
    priority,
    dedupe_key,
    reason,
    required=True,
    depends_on_dedupe_keys=None,
    parent_dedupe_key=None,
    allowed_tools=None,
    expected_evidence=None,
    max_tool_steps=None,
):
    task = {
        "agent": agent,
        "task_type": task_type,
        "goal": goal,
        "depends_on_dedupe_keys": list(depends_on_dedupe_keys or []),
        "result_key": result_key,
        "priority": priority,
        "required": bool(required),
        "dedupe_key": dedupe_key,
        "parent_dedupe_key": parent_dedupe_key,
        "reason": reason,
        "allowed_tools": list(allowed_tools or []),
        "expected_evidence": list(expected_evidence or []),
    }
    if max_tool_steps is not None:
        task["max_tool_steps"] = max_tool_steps
    return task


def _dedupe_tasks(tasks):
    seen = set()
    result = []
    for task in tasks:
        key = task.get("dedupe_key") or task.get("task_id")
        if key in seen:
            continue
        seen.add(key)
        result.append(task)
    return result


def should_search_medical_knowledge(state):
    return _contains_any(_message(state), KNOWLEDGE_KEYWORDS)


def should_route_patient_data(state):
    message = _message(state)
    return _contains_any(message, PATIENT_DATA_KEYWORDS + RECORD_KEYWORDS + VISIT_KEYWORDS)


def should_route_image_analysis(state):
    if not state.get("image_id"):
        return False
    return _contains_any(_message(state), IMAGE_REFERENCE_KEYWORDS + IMAGE_KEYWORDS)


def build_risk_flags(state):
    message = _message(state)
    return [keyword for keyword in RISK_KEYWORDS if keyword in message]


def build_task_board(state, memory_enabled=False):
    tasks = []
    if memory_enabled and state.get("patient_id"):
        tasks.append(
            _make_task(
                GRAPH_MEMORY,
                "memory_retrieval",
                "Recall relevant long-term patient memory.",
                "memory_result",
                95,
                "memory:patient_context",
                "Long-term memory is enabled for the verified patient.",
                required=False,
                allowed_tools=["memory.recall_long_term_memories"],
                expected_evidence=["Relevant long-term memory for the current patient."],
                max_tool_steps=1,
            )
        )
    if should_route_patient_data(state):
        tasks.append(
            _make_task(
                GRAPH_PATIENT_DATA,
                "patient_data_lookup",
                "Retrieve patient profile, medical record, or visit data.",
                "patient_data_result",
                90,
                "patient_data:structured_context",
                "The request references patient-specific structured data.",
                allowed_tools=[
                    "patient.get_patient_profile",
                    "visit.search_visits",
                    "medical_record.search_records",
                ],
                expected_evidence=["Verified patient profile, visit, or medical record facts."],
                max_tool_steps=4,
            )
        )
    if should_route_image_analysis(state):
        tasks.append(
            _make_task(
                GRAPH_IMAGE_ANALYSIS,
                "image_analysis",
                "Analyze the uploaded image or report attachment.",
                "image_analysis_result",
                85,
                "image_analysis:uploaded_image",
                "The request references an uploaded image.",
                allowed_tools=["image.analyze_uploaded_image"],
                expected_evidence=["Visible findings and limitations from the uploaded image."],
                max_tool_steps=1,
            )
        )
    if should_search_medical_knowledge(state):
        tasks.append(
            _make_task(
                GRAPH_MEDICAL_KNOWLEDGE_AGENT,
                "medical_knowledge_lookup",
                "Retrieve relevant local medical knowledge.",
                "medical_knowledge_result",
                80,
                "medical_knowledge:query",
                "The request asks for general medical knowledge or test indicator explanation.",
                required=False,
                allowed_tools=[
                    "medical_knowledge.search",
                    "medical_knowledge.deep_retrieve",
                ],
                expected_evidence=["General medical knowledge with local sources."],
                max_tool_steps=2,
            )
        )
    return normalize_planned_tasks(_dedupe_tasks(tasks), max_tasks=state.get("max_tasks") or 8)


def completed_task_ids(state):
    return {
        task.get("task_id")
        for task in state.get("task_board") or []
        if task.get("status") in ("done", "skipped")
    }


def find_ready_tasks(state):
    completed = completed_task_ids(state)
    ready = []
    for task in state.get("task_board") or []:
        if task.get("status") != "pending":
            continue
        depends_on = task.get("depends_on") or []
        if all(task_id in completed for task_id in depends_on):
            ready.append(task)
    ready.sort(key=lambda item: (-(item.get("priority") or 0), item.get("task_id") or ""))
    return ready


def start_next_ready_task(state):
    selected, task_board = start_ready_tasks(state, max_parallel_tasks=1)
    if not selected:
        return None, list(state.get("task_board") or [])
    return selected[0], task_board


def start_ready_tasks(state, max_parallel_tasks=None):
    ready = find_ready_tasks(state)
    limit = max_parallel_tasks if max_parallel_tasks is not None else state.get("max_parallel_tasks")
    try:
        limit = int(limit or len(ready) or 1)
    except (TypeError, ValueError):
        limit = len(ready) or 1
    limit = max(1, limit)
    selected = ready[:limit]
    if not selected:
        return [], list(state.get("task_board") or [])

    selected_ids = {task.get("task_id") for task in selected}
    selected_by_id = {}
    updated = []
    dispatch_round = state.get("dispatch_round") or 0
    for task in state.get("task_board") or []:
        item = dict(task)
        if item.get("task_id") in selected_ids:
            item["status"] = "running"
            item["dispatch_round"] = dispatch_round
            selected_by_id[item.get("task_id")] = item
        updated.append(item)

    ordered_selected = [selected_by_id[task.get("task_id")] for task in selected if task.get("task_id") in selected_by_id]
    return ordered_selected, updated


def summarize_task_board(task_board):
    summary = {"done": 0, "failed": 0, "pending": 0, "running": 0, "skipped": 0, "required_failed": False}
    for task in task_board or []:
        status = task.get("status") or "pending"
        if status not in summary:
            summary[status] = 0
        summary[status] += 1
        if status == "failed" and task.get("required"):
            summary["required_failed"] = True
    return summary


def route_after_dispatcher(state):
    dispatched = state.get("dispatched_tasks") or []
    if not dispatched:
        return GRAPH_JOIN
    sends = []
    for task in dispatched:
        branch_state = dict(state)
        branch_state["current_task"] = task
        sends.append(Send(task.get("agent"), branch_state))
    return sends


def route_after_gap_check(state):
    return "continue" if state.get("need_more_tasks") else "finish"


def route_after_router(state):
    plan = state.get("plan") or []
    if GRAPH_MEDICAL_KNOWLEDGE in plan or GRAPH_MEDICAL_KNOWLEDGE_AGENT in plan:
        return GRAPH_MEDICAL_KNOWLEDGE
    return GRAPH_COMPOSER


def route_after_medical_knowledge(state):
    return GRAPH_COMPOSER
