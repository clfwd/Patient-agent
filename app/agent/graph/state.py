"""Shared state constants for the LangGraph patient agent pipeline."""

from app.agent.state import AgentState


GRAPH_PREFLIGHT = "graph_preflight"
GRAPH_ROUTER = "graph_router"
GRAPH_PLANNER = "graph_planner"
GRAPH_DISPATCHER = "graph_dispatcher"
GRAPH_MEMORY = "graph_memory_agent"
GRAPH_PATIENT_DATA = "graph_patient_data_agent"
GRAPH_IMAGE_ANALYSIS = "graph_image_analysis_agent"
GRAPH_MEDICAL_KNOWLEDGE = "graph_medical_knowledge"
GRAPH_MEDICAL_KNOWLEDGE_AGENT = "graph_medical_knowledge_agent"
GRAPH_JOIN = "graph_join"
GRAPH_GAP_CHECKER = "graph_gap_checker"
GRAPH_COMPOSER = "graph_composer"
GRAPH_POSTPROCESS = "graph_postprocess"

GRAPH_PLAN = [GRAPH_PREFLIGHT, GRAPH_PLANNER, GRAPH_DISPATCHER, GRAPH_JOIN, GRAPH_GAP_CHECKER, GRAPH_COMPOSER, GRAPH_POSTPROCESS]


__all__ = [
    "AgentState",
    "GRAPH_COMPOSER",
    "GRAPH_DISPATCHER",
    "GRAPH_GAP_CHECKER",
    "GRAPH_IMAGE_ANALYSIS",
    "GRAPH_JOIN",
    "GRAPH_MEMORY",
    "GRAPH_MEDICAL_KNOWLEDGE",
    "GRAPH_MEDICAL_KNOWLEDGE_AGENT",
    "GRAPH_PLAN",
    "GRAPH_POSTPROCESS",
    "GRAPH_PREFLIGHT",
    "GRAPH_PATIENT_DATA",
    "GRAPH_PLANNER",
    "GRAPH_ROUTER",
]
