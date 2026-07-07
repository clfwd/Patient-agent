"""Build and run the task-board LangGraph patient agent pipeline."""

from langgraph.graph import END, StateGraph

from .nodes import (
    graph_composer_node,
    graph_dispatcher_node,
    graph_gap_checker_node,
    graph_image_analysis_agent_node,
    graph_join_node,
    graph_medical_knowledge_agent_node,
    graph_memory_agent_node,
    graph_patient_data_agent_node,
    graph_planner_node,
    graph_postprocess_node,
    graph_preflight_node,
)
from .router import route_after_dispatcher, route_after_gap_check
from .state import (
    AgentState,
    GRAPH_COMPOSER,
    GRAPH_DISPATCHER,
    GRAPH_GAP_CHECKER,
    GRAPH_IMAGE_ANALYSIS,
    GRAPH_JOIN,
    GRAPH_MEDICAL_KNOWLEDGE_AGENT,
    GRAPH_MEMORY,
    GRAPH_PATIENT_DATA,
    GRAPH_PLANNER,
    GRAPH_POSTPROCESS,
    GRAPH_PREFLIGHT,
)


def build_agent_graph(service):
    workflow = StateGraph(AgentState)
    workflow.add_node(GRAPH_PREFLIGHT, lambda state: graph_preflight_node(service, state))
    workflow.add_node(GRAPH_PLANNER, lambda state: graph_planner_node(service, state))
    workflow.add_node(GRAPH_DISPATCHER, lambda state: graph_dispatcher_node(service, state))
    workflow.add_node(GRAPH_MEMORY, lambda state: graph_memory_agent_node(service, state))
    workflow.add_node(GRAPH_PATIENT_DATA, lambda state: graph_patient_data_agent_node(service, state))
    workflow.add_node(GRAPH_IMAGE_ANALYSIS, lambda state: graph_image_analysis_agent_node(service, state))
    workflow.add_node(GRAPH_MEDICAL_KNOWLEDGE_AGENT, lambda state: graph_medical_knowledge_agent_node(service, state))
    workflow.add_node(GRAPH_JOIN, lambda state: graph_join_node(service, state))
    workflow.add_node(GRAPH_GAP_CHECKER, lambda state: graph_gap_checker_node(service, state))
    workflow.add_node(GRAPH_COMPOSER, lambda state: graph_composer_node(service, state))
    workflow.add_node(GRAPH_POSTPROCESS, lambda state: graph_postprocess_node(service, state))

    workflow.set_entry_point(GRAPH_PREFLIGHT)
    workflow.add_edge(GRAPH_PREFLIGHT, GRAPH_PLANNER)
    workflow.add_edge(GRAPH_PLANNER, GRAPH_DISPATCHER)
    workflow.add_conditional_edges(GRAPH_DISPATCHER, route_after_dispatcher)
    workflow.add_edge(GRAPH_MEMORY, GRAPH_JOIN)
    workflow.add_edge(GRAPH_PATIENT_DATA, GRAPH_JOIN)
    workflow.add_edge(GRAPH_IMAGE_ANALYSIS, GRAPH_JOIN)
    workflow.add_edge(GRAPH_MEDICAL_KNOWLEDGE_AGENT, GRAPH_JOIN)
    workflow.add_edge(GRAPH_JOIN, GRAPH_GAP_CHECKER)
    workflow.add_conditional_edges(
        GRAPH_GAP_CHECKER,
        route_after_gap_check,
        {
            "continue": GRAPH_DISPATCHER,
            "finish": GRAPH_COMPOSER,
        },
    )
    workflow.add_edge(GRAPH_COMPOSER, GRAPH_POSTPROCESS)
    workflow.add_edge(GRAPH_POSTPROCESS, END)
    return workflow.compile()


def run_agent_graph(service, state):
    graph = build_agent_graph(service)
    return graph.invoke(dict(state))
