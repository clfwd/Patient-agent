"""Server-owned agent and tool capability registry for graph planning."""

from dataclasses import dataclass
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
    return item


def validate_task_board(tasks, max_tasks=8):
    cleaned = []
    seen_task_ids = set()
    seen_dedupe = set()
    for task in tasks or []:
        item = apply_server_tool_policy(task)
        if item is None:
            continue
        task_id = item.get("task_id")
        dedupe_key = item.get("dedupe_key")
        if not task_id or not dedupe_key or task_id in seen_task_ids or dedupe_key in seen_dedupe:
            continue
        seen_task_ids.add(task_id)
        seen_dedupe.add(dedupe_key)
        cleaned.append(item)
        if len(cleaned) >= max_tasks:
            break
    valid_ids = {task["task_id"] for task in cleaned}
    for task in cleaned:
        task["depends_on"] = [task_id for task_id in task.get("depends_on") or [] if task_id in valid_ids]
    return cleaned
