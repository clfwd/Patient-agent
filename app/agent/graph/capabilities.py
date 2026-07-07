"""Server-owned agent and tool capability registry for graph planning."""

from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Tuple

from .state import GRAPH_IMAGE_ANALYSIS, GRAPH_MEDICAL_KNOWLEDGE_AGENT, GRAPH_MEMORY, GRAPH_PATIENT_DATA


PATIENT_DATA_TOOLS = (
    "patient.get_patient_profile",
    "visit.search_visits",
    "medical_record.search_records",
)
MEDICAL_KNOWLEDGE_TOOLS = (
    "medical_knowledge.search",
    "medical_knowledge.deep_retrieve",
)
IMAGE_ANALYSIS_TOOLS = ("image.analyze_uploaded_image",)
MEMORY_TOOLS = ("memory.recall_long_term_memories",)


@dataclass(frozen=True)
class AgentCapability:
    agent_name: str
    agent_type: str
    description: str
    allowed_tools: Tuple[str, ...]
    default_max_tool_steps: int
    max_tool_steps_cap: int
    input_requirements: Tuple[str, ...]
    output_schema: str
    risk_boundary: Tuple[str, ...]


CAPABILITY_REGISTRY: Dict[str, AgentCapability] = {
    GRAPH_PATIENT_DATA: AgentCapability(
        agent_name=GRAPH_PATIENT_DATA,
        agent_type="controlled_react_worker_agent",
        description="Retrieves verified-patient profile, visit, and medical record facts.",
        allowed_tools=PATIENT_DATA_TOOLS,
        default_max_tool_steps=4,
        max_tool_steps_cap=5,
        input_requirements=("verified_patient",),
        output_schema="WorkerEvidence(patient_specific=True)",
        risk_boundary=("current verified patient only", "no diagnosis", "no image/knowledge/memory tools"),
    ),
    GRAPH_MEDICAL_KNOWLEDGE_AGENT: AgentCapability(
        agent_name=GRAPH_MEDICAL_KNOWLEDGE_AGENT,
        agent_type="controlled_react_worker_agent",
        description="Retrieves and compresses local medical knowledge with sources.",
        allowed_tools=MEDICAL_KNOWLEDGE_TOOLS,
        default_max_tool_steps=2,
        max_tool_steps_cap=2,
        input_requirements=("message",),
        output_schema="WorkerEvidence(medical_knowledge=True)",
        risk_boundary=("general knowledge only", "no patient data tools", "no diagnosis"),
    ),
    GRAPH_IMAGE_ANALYSIS: AgentCapability(
        agent_name=GRAPH_IMAGE_ANALYSIS,
        agent_type="single_shot_worker",
        description="Analyzes one verified uploaded image/report.",
        allowed_tools=IMAGE_ANALYSIS_TOOLS,
        default_max_tool_steps=1,
        max_tool_steps_cap=1,
        input_requirements=("image_id", "verified_patient"),
        output_schema="WorkerEvidence(source_type=image_analysis)",
        risk_boundary=("current verified patient image only",),
    ),
    GRAPH_MEMORY: AgentCapability(
        agent_name=GRAPH_MEMORY,
        agent_type="single_shot_worker",
        description="Recalls long-term memory relevant to the current verified patient.",
        allowed_tools=MEMORY_TOOLS,
        default_max_tool_steps=1,
        max_tool_steps_cap=1,
        input_requirements=("patient_id",),
        output_schema="WorkerEvidence(source_type=memory)",
        risk_boundary=("memory is historical context, not current fact",),
    ),
}


RUNTIME_ALLOWED_TOOLS = set(PATIENT_DATA_TOOLS + MEDICAL_KNOWLEDGE_TOOLS + IMAGE_ANALYSIS_TOOLS + MEMORY_TOOLS)
TASK_ID_PATTERN = re.compile(r"^[a-z0-9_]+:[a-z0-9_:-]+$")
DEDUPE_KEY_PATTERN = re.compile(r"^[a-z0-9_:-]{1,128}$")
TASK_TYPE_PATTERN = re.compile(r"^[a-z0-9_:-]{1,64}$")
TASK_ID_PREFIX_BY_AGENT = {
    GRAPH_PATIENT_DATA: "patient_data",
    GRAPH_MEDICAL_KNOWLEDGE_AGENT: "medical_knowledge",
    GRAPH_IMAGE_ANALYSIS: "image_analysis",
    GRAPH_MEMORY: "memory",
}


class TaskBoardValidationError(ValueError):
    def __init__(self, message, rejected_tasks=None):
        super().__init__(message)
        self.rejected_tasks = list(rejected_tasks or [])


def registry_for_prompt():
    return [
        {
            "agent_name": item.agent_name,
            "agent_type": item.agent_type,
            "description": item.description,
            "allowed_tools": list(item.allowed_tools),
            "default_max_tool_steps": item.default_max_tool_steps,
            "max_tool_steps_cap": item.max_tool_steps_cap,
            "input_requirements": list(item.input_requirements),
            "output_schema": item.output_schema,
            "risk_boundary": list(item.risk_boundary),
        }
        for item in CAPABILITY_REGISTRY.values()
    ]


def effective_tools(agent_name: str, requested_tools: Iterable[str]) -> List[str]:
    capability = CAPABILITY_REGISTRY.get(agent_name)
    if capability is None:
        return []
    requested = set(requested_tools or capability.allowed_tools)
    return [tool for tool in capability.allowed_tools if tool in requested and tool in RUNTIME_ALLOWED_TOOLS]


def effective_max_steps(agent_name: str, requested_steps=None) -> int:
    capability = CAPABILITY_REGISTRY.get(agent_name)
    if capability is None:
        return 1
    try:
        requested = int(requested_steps or capability.default_max_tool_steps)
    except (TypeError, ValueError):
        requested = capability.default_max_tool_steps
    return max(1, min(requested, capability.max_tool_steps_cap))


def task_prefix_for_agent(agent_name):
    return TASK_ID_PREFIX_BY_AGENT.get(agent_name)


def slug_task_key(value):
    raw = str(value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    return slug or "task"


def generate_task_id(agent_name, dedupe_key, existing_ids=None):
    prefix = task_prefix_for_agent(agent_name)
    if not prefix:
        raise ValueError("unknown agent: {0}".format(agent_name))
    existing = set(existing_ids or [])
    slug = slug_task_key(dedupe_key)
    index = 1
    while True:
        task_id = "{0}:{1}:{2}".format(prefix, slug, index)
        if task_id not in existing:
            return task_id
        index += 1


def apply_server_tool_policy(task):
    """Treat LLM tool choices as intent; only server registry grants actual tools."""
    item = dict(task)
    capability = CAPABILITY_REGISTRY.get(item.get("agent"))
    if capability is None:
        return None
    item["allowed_tools"] = list(item.get("allowed_tools") or capability.allowed_tools)
    item["effective_allowed_tools"] = effective_tools(item["agent"], item["allowed_tools"])
    if not item["effective_allowed_tools"]:
        return None
    item["max_tool_steps"] = item.get("max_tool_steps") or capability.default_max_tool_steps
    item["effective_max_tool_steps"] = effective_max_steps(item["agent"], item.get("max_tool_steps"))
    if not item.get("result_key"):
        prefix = task_prefix_for_agent(item["agent"]) or item["agent"]
        item["result_key"] = "{0}_result".format(prefix)
    return item


def _rejection(task, reason, detail):
    return {
        "task_id": task.get("task_id"),
        "dedupe_key": task.get("dedupe_key"),
        "reason": reason,
        "detail": detail,
    }


def _validate_task_identity(item):
    task_id = str(item.get("task_id") or "").strip()
    dedupe_key = str(item.get("dedupe_key") or "").strip()
    if not task_id:
        return "invalid_task_id", "task_id is required"
    if not TASK_ID_PATTERN.match(task_id):
        return "invalid_task_id", "task_id must match {0}".format(TASK_ID_PATTERN.pattern)
    expected_prefix = TASK_ID_PREFIX_BY_AGENT.get(item.get("agent"))
    if expected_prefix and not task_id.startswith(expected_prefix + ":"):
        return "invalid_task_id_prefix", "task_id prefix must be {0}: for {1}".format(expected_prefix, item.get("agent"))
    dedupe_error = _dedupe_key_error(dedupe_key)
    if dedupe_error:
        return "invalid_dedupe_key", dedupe_error
    return None, None


def _dedupe_key_error(dedupe_key):
    if not dedupe_key:
        return "dedupe_key is required"
    if not DEDUPE_KEY_PATTERN.match(dedupe_key):
        return "dedupe_key must match {0}".format(DEDUPE_KEY_PATTERN.pattern)
    parts = str(dedupe_key).split(":")
    if len(parts) < 2:
        return "dedupe_key must use domain:purpose[:scope] format"
    for segment in parts:
        tokens = [token for token in segment.split("_") if token]
        if len(tokens) >= 5:
            return "dedupe_key segment looks like a natural-language summary: {0}".format(segment)
    return None


def _validate_semantic_task(item):
    dedupe_key = str(item.get("dedupe_key") or "").strip()
    task_type = str(item.get("task_type") or "general").strip()
    dedupe_error = _dedupe_key_error(dedupe_key)
    if dedupe_error:
        return "invalid_dedupe_key", dedupe_error
    if not task_type or not TASK_TYPE_PATTERN.match(task_type):
        return "invalid_task_type", "task_type must match {0}".format(TASK_TYPE_PATTERN.pattern)
    legacy_depends_on = item.get("depends_on")
    depends_on_dedupe_keys = list(item.get("depends_on_dedupe_keys") or [])
    if legacy_depends_on and not depends_on_dedupe_keys:
        return "legacy_depends_on_not_allowed", "depends_on is an internal field; use depends_on_dedupe_keys"
    for key in depends_on_dedupe_keys:
        dep_error = _dedupe_key_error(str(key or ""))
        if dep_error:
            return "invalid_depends_on_dedupe_key", "depends_on_dedupe_keys contains invalid key {0}: {1}".format(key, dep_error)
    return None, None


def _has_dependency_cycle(tasks):
    task_by_id = {task.get("task_id"): task for task in tasks}
    visiting = set()
    visited = set()

    def visit(task_id):
        if task_id in visiting:
            return True
        if task_id in visited:
            return False
        task = task_by_id.get(task_id)
        if task is None:
            return False
        visiting.add(task_id)
        for dep in task.get("depends_on") or []:
            if dep in task_by_id and visit(dep):
                return True
        visiting.remove(task_id)
        visited.add(task_id)
        return False

    return any(visit(task_id) for task_id in task_by_id)


def validate_task_board(tasks, max_tasks=8):
    cleaned = []
    seen_task_ids = set()
    seen_dedupe = set()
    rejected = []
    for task in tasks or []:
        item = apply_server_tool_policy(task)
        if item is None:
            rejected.append(_rejection(task, "invalid_capability", "agent or allowed_tools are not permitted"))
            break
        task_id = item.get("task_id")
        dedupe_key = item.get("dedupe_key")
        reason, detail = _validate_task_identity(item)
        if reason:
            rejected.append(_rejection(item, reason, detail))
            break
        if task_id in seen_task_ids:
            rejected.append(_rejection(item, "duplicate_task_id", "task_id is duplicated in task board"))
            break
        if dedupe_key in seen_dedupe:
            rejected.append(_rejection(item, "duplicate_dedupe_key", "dedupe_key is duplicated in task board"))
            break
        seen_task_ids.add(task_id)
        seen_dedupe.add(dedupe_key)
        cleaned.append(item)
        if len(cleaned) >= max_tasks:
            break
    valid_ids = {task["task_id"] for task in cleaned}
    for task in cleaned:
        depends_on = list(task.get("depends_on") or [])
        for task_id in depends_on:
            if task_id == task.get("task_id"):
                rejected.append(_rejection(task, "self_dependency", "task cannot depend on itself"))
                break
            if task_id not in valid_ids:
                rejected.append(_rejection(task, "invalid_dependency", "depends_on references missing task_id: {0}".format(task_id)))
                break
        if rejected:
            break
        task["depends_on"] = depends_on
    if not rejected and _has_dependency_cycle(cleaned):
        rejected.append({"task_id": None, "dedupe_key": None, "reason": "dependency_cycle", "detail": "task_board contains a depends_on cycle"})
    if rejected:
        raise TaskBoardValidationError(rejected[0]["detail"], rejected)
    return cleaned


def _normalize_semantic_tasks(tasks, existing_tasks=None, max_tasks=8, strict=True, created_by="graph_planner"):
    existing_tasks = list(existing_tasks or [])
    existing_ids = {task.get("task_id") for task in existing_tasks if task.get("task_id")}
    existing_dedupe = {task.get("dedupe_key") for task in existing_tasks if task.get("dedupe_key")}
    existing_by_dedupe = {
        task.get("dedupe_key"): task.get("task_id")
        for task in existing_tasks
        if task.get("dedupe_key") and task.get("task_id")
    }
    generated_ids = set(existing_ids)
    candidates = []
    rejected = []
    seen_dedupe = set()

    for task in tasks or []:
        raw = task.dict() if hasattr(task, "dict") else dict(task or {})
        reason, detail = _validate_semantic_task(raw)
        if reason:
            rejected.append(_rejection(raw, reason, detail))
            if strict:
                break
            continue
        dedupe_key = raw.get("dedupe_key")
        if dedupe_key in existing_dedupe or dedupe_key in seen_dedupe:
            rejected.append(_rejection(raw, "duplicate_dedupe_key", "dedupe_key conflicts with existing or proposed task"))
            if strict:
                break
            continue
        item = dict(raw)
        try:
            item["task_id"] = generate_task_id(item.get("agent"), dedupe_key, existing_ids=generated_ids)
        except ValueError as exc:
            rejected.append(_rejection(raw, "invalid_capability", str(exc)))
            if strict:
                break
            continue
        item["status"] = item.get("status") or "pending"
        item["depends_on"] = []
        item["depends_on_dedupe_keys"] = list(item.get("depends_on_dedupe_keys") or [])
        item["created_by"] = item.get("created_by") or created_by
        item["parent_task_id"] = None
        item["retry_count"] = item.get("retry_count") or 0
        item["max_retries"] = item.get("max_retries") if item.get("max_retries") is not None else 1
        item["timeout_seconds"] = item.get("timeout_seconds") or 20
        item["server_generated_task_id"] = True
        item = apply_server_tool_policy(item)
        if item is None:
            rejected.append(_rejection(raw, "invalid_capability", "agent or allowed_tools are not permitted"))
            if strict:
                break
            continue
        generated_ids.add(item["task_id"])
        seen_dedupe.add(dedupe_key)
        candidates.append(item)

    if strict and rejected:
        raise TaskBoardValidationError(rejected[0]["detail"], rejected)

    selected = candidates[:max_tasks]
    selected_by_dedupe = {task.get("dedupe_key"): task.get("task_id") for task in selected}
    allowed_by_dedupe = dict(existing_by_dedupe)
    allowed_by_dedupe.update(selected_by_dedupe)
    resolved = []
    for task in selected:
        depends_on = []
        invalid = None
        for dedupe_key in task.get("depends_on_dedupe_keys") or []:
            if dedupe_key == task.get("dedupe_key"):
                invalid = _rejection(task, "self_dependency", "task cannot depend on itself")
                break
            task_id = allowed_by_dedupe.get(dedupe_key)
            if not task_id:
                reason = "dependency_not_accepted" if dedupe_key in {item.get("dedupe_key") for item in candidates} else "invalid_depends_on_dedupe_key"
                detail = "depends_on_dedupe_keys references missing or unaccepted dedupe_key: {0}".format(dedupe_key)
                invalid = _rejection(task, reason, detail)
                break
            depends_on.append(task_id)
        if invalid:
            rejected.append(invalid)
            if strict:
                break
            continue
        task["depends_on"] = depends_on
        resolved.append(task)

    proposed_for_cycle = existing_tasks + resolved
    if not rejected and _has_dependency_cycle(proposed_for_cycle):
        rejected.append({"task_id": None, "dedupe_key": None, "reason": "dependency_cycle", "detail": "task_board contains a depends_on cycle"})

    if strict and rejected:
        raise TaskBoardValidationError(rejected[0]["detail"], rejected)
    if not strict and _has_dependency_cycle(proposed_for_cycle):
        rejected.extend(
            _rejection(task, "dependency_cycle", "proposed tasks would create a depends_on cycle")
            for task in resolved
        )
        resolved = []

    return resolved, rejected


def normalize_planned_tasks(tasks, max_tasks=8):
    normalized, rejected = _normalize_semantic_tasks(tasks, max_tasks=max_tasks, strict=True, created_by="graph_planner")
    if rejected:
        raise TaskBoardValidationError(rejected[0]["detail"], rejected)
    return normalized


def normalize_proposed_tasks(tasks, existing_tasks=None, max_tasks=2):
    return _normalize_semantic_tasks(
        tasks,
        existing_tasks=existing_tasks,
        max_tasks=max_tasks,
        strict=False,
        created_by="graph_gap_checker",
    )


def validate_proposed_tasks(tasks, existing_tasks=None, max_tasks=2):
    existing_tasks = list(existing_tasks or [])
    existing_ids = {task.get("task_id") for task in existing_tasks if task.get("task_id")}
    existing_dedupe = {task.get("dedupe_key") for task in existing_tasks if task.get("dedupe_key")}
    candidates = []
    rejected = []
    seen_task_ids = set()
    seen_dedupe = set()

    for task in tasks or []:
        item = apply_server_tool_policy(task)
        if item is None:
            rejected.append(_rejection(task, "invalid_capability", "agent or allowed_tools are not permitted"))
            continue
        task_id = item.get("task_id")
        dedupe_key = item.get("dedupe_key")
        reason, detail = _validate_task_identity(item)
        if reason:
            rejected.append(_rejection(item, reason, detail))
            continue
        if task_id in existing_ids or task_id in seen_task_ids:
            rejected.append(_rejection(item, "duplicate_task_id", "task_id conflicts with existing or proposed task"))
            continue
        if dedupe_key in existing_dedupe or dedupe_key in seen_dedupe:
            rejected.append(_rejection(item, "duplicate_dedupe_key", "dedupe_key conflicts with existing or proposed task"))
            continue
        seen_task_ids.add(task_id)
        seen_dedupe.add(dedupe_key)
        candidates.append(item)

    allowed_dependency_ids = existing_ids | {task.get("task_id") for task in candidates}
    valid_candidates = []
    for task in candidates:
        depends_on = list(task.get("depends_on") or [])
        invalid = None
        for task_id in depends_on:
            if task_id == task.get("task_id"):
                invalid = _rejection(task, "self_dependency", "task cannot depend on itself")
                break
            if task_id not in allowed_dependency_ids:
                invalid = _rejection(task, "invalid_dependency", "depends_on references missing task_id: {0}".format(task_id))
                break
        if invalid:
            rejected.append(invalid)
            continue
        task["depends_on"] = depends_on
        valid_candidates.append(task)

    proposed_for_cycle = existing_tasks + valid_candidates
    if _has_dependency_cycle(proposed_for_cycle):
        proposed_ids = {task.get("task_id") for task in valid_candidates}
        rejected.extend(
            _rejection(task, "dependency_cycle", "proposed tasks would create a depends_on cycle")
            for task in valid_candidates
            if task.get("task_id") in proposed_ids
        )
        valid_candidates = []

    selected = valid_candidates[:max_tasks]
    selected_ids = existing_ids | {task.get("task_id") for task in selected}
    accepted = []
    for task in selected:
        missing_selected_deps = [task_id for task_id in task.get("depends_on") or [] if task_id not in selected_ids]
        if missing_selected_deps:
            rejected.append(
                _rejection(
                    task,
                    "dependency_not_accepted",
                    "depends_on references task outside accepted budget: {0}".format(missing_selected_deps[0]),
                )
            )
            continue
        accepted.append(task)

    return accepted, rejected
