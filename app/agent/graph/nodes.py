"""LangGraph node wrappers around the existing patient agent service."""

from app.agent.tools import AgentToolExecutor, AgentToolValidationError
from app.tool_routing import build_heuristic_tool_selection

from .router import build_risk_flags, build_task_board, find_ready_tasks, start_next_ready_task, summarize_task_board
from .state import (
    GRAPH_COMPOSER,
    GRAPH_DISPATCHER,
    GRAPH_GAP_CHECKER,
    GRAPH_IMAGE_ANALYSIS,
    GRAPH_JOIN,
    GRAPH_MEDICAL_KNOWLEDGE,
    GRAPH_MEDICAL_KNOWLEDGE_AGENT,
    GRAPH_MEMORY,
    GRAPH_PATIENT_DATA,
    GRAPH_PLANNER,
    GRAPH_POSTPROCESS,
    GRAPH_PREFLIGHT,
    GRAPH_ROUTER,
)


def _append_unique(values, value):
    result = list(values or [])
    if value not in result:
        result.append(value)
    return result


def _format_knowledge_sources(hits):
    sources = []
    seen = set()
    for hit in hits or []:
        title = hit.get("title")
        source = hit.get("source")
        if not title or not source:
            continue
        key = (title, source)
        if key in seen:
            continue
        seen.add(key)
        sources.append("- {0} - {1}".format(title, source))
    if not sources:
        return ""
    return "参考来源：\n{0}".format("\n".join(sources))


def _current_task(state, agent):
    task = state.get("current_task") or {}
    if not task:
        task = {
            "task_id": "{0}:adhoc".format(agent),
            "agent": agent,
            "result_key": "{0}_result".format(agent),
            "required": False,
        }
    return task


def _worker_success(state, task, result, evidence_items=None, status="done"):
    task_id = task.get("task_id")
    return {
        "task_results": dict(list((state.get("task_results") or {}).items()) + [(task_id, result)]),
        "worker_events": list(state.get("worker_events") or [])
        + [
            {
                "task_id": task_id,
                "agent": task.get("agent"),
                "status": status,
                "dispatch_round": state.get("dispatch_round") or 0,
                "result_key": task.get("result_key"),
            }
        ],
        "evidence_items": list(state.get("evidence_items") or []) + list(evidence_items or []),
    }


def _worker_failure(state, task, error):
    message = str(error)
    task_id = task.get("task_id")
    return {
        "task_results": dict(list((state.get("task_results") or {}).items()) + [(task_id, {"error": message})]),
        "worker_events": list(state.get("worker_events") or [])
        + [
            {
                "task_id": task_id,
                "agent": task.get("agent"),
                "status": "failed",
                "dispatch_round": state.get("dispatch_round") or 0,
                "result_key": task.get("result_key"),
                "error": message,
            }
        ],
        "errors": list(state.get("errors") or []) + [message],
    }


def _tool_context(state):
    return {
        "patient_id": state.get("patient_id"),
        "patient_no": state.get("patient_no"),
        "visit_no": state.get("visit_no"),
        "image_id": state.get("image_id"),
        "metadata": state.get("metadata") or {},
    }


def graph_preflight_node(service, state):
    current_state = dict(state)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "Entering LangGraph preflight node.",
        stage=GRAPH_PREFLIGHT,
    )
    preflight_state = dict(current_state)
    preflight_state["skip_long_term_memory_preflight"] = True
    current_state.update(service._preflight_node(preflight_state))
    current_state["conversation_history"] = service._load_conversation_history(current_state.get("session_id"))
    service._record_user_message(current_state)
    current_state["plan"] = [GRAPH_PREFLIGHT]
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "completed",
        "LangGraph preflight node completed.",
        stage=GRAPH_PREFLIGHT,
    )
    return current_state


def graph_planner_node(service, state):
    current_state = dict(state)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "Building LangGraph task board.",
        stage=GRAPH_PLANNER,
    )
    task_board = build_task_board(current_state, memory_enabled=getattr(service, "memory_service", None) is not None)
    risk_flags = build_risk_flags(current_state)
    current_state["task_board"] = task_board
    current_state["risk_flags"] = _append_unique(current_state.get("risk_flags") or [], risk_flags[0]) if risk_flags else list(current_state.get("risk_flags") or [])
    for flag in risk_flags[1:]:
        current_state["risk_flags"] = _append_unique(current_state["risk_flags"], flag)
    current_state["plan"] = _append_unique(current_state.get("plan") or [], GRAPH_PLANNER)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "completed",
        "LangGraph planner created {0} task(s).".format(len(task_board)),
        stage=GRAPH_PLANNER,
    )
    return current_state


def graph_router_node(service, state):
    current_state = graph_planner_node(service, state)
    current_state["plan"] = _append_unique(current_state.get("plan") or [], GRAPH_ROUTER)
    return current_state


def graph_dispatcher_node(service, state):
    current_state = dict(state)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "Selecting the next ready task.",
        stage=GRAPH_DISPATCHER,
    )
    task, task_board = start_next_ready_task(current_state)
    current_state["task_board"] = task_board
    current_state["current_task"] = task
    current_state["plan"] = _append_unique(current_state.get("plan") or [], GRAPH_DISPATCHER)
    detail = "No ready task found." if task is None else "Dispatching task {0}.".format(task.get("task_id"))
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "completed",
        detail,
        stage=GRAPH_DISPATCHER,
    )
    return current_state


def graph_patient_data_agent_node(service, state):
    current_state = dict(state)
    task = _current_task(current_state, GRAPH_PATIENT_DATA)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "Executing patient data worker.",
        stage=GRAPH_PATIENT_DATA,
    )
    try:
        selection = build_heuristic_tool_selection(current_state.get("message") or "", context=_tool_context(current_state))
        tool_name = selection["tool_name"]
        if tool_name == "image.analyze_uploaded_image":
            tool_name = "patient.get_patient_profile"
            arguments = {"patient_id": current_state.get("patient_id"), "patient_no": current_state.get("patient_no")}
        else:
            arguments = selection.get("arguments") or {}
        executor = AgentToolExecutor(service.mcp_registry, service.session_factory, current_state)
        result = executor.invoke(tool_name, arguments)
        evidence_items = [
            {
                "evidence_id": "ev:{0}".format(task.get("task_id")),
                "source_task_id": task.get("task_id"),
                "source_agent": GRAPH_PATIENT_DATA,
                "evidence_type": "patient_data",
                "content": result,
                "source": tool_name,
                "confidence": 1.0,
                "risk_level": "low",
            }
        ]
        current_state.update(_worker_success(current_state, task, {"tool_name": tool_name, "result": result}, evidence_items))
        current_state["agent_trace"] = service._append_trace(
            current_state,
            "graph",
            "completed",
            "Patient data worker completed.",
            stage=GRAPH_PATIENT_DATA,
        )
    except (AgentToolValidationError, Exception) as exc:
        current_state.update(_worker_failure(current_state, task, exc))
        current_state["agent_trace"] = service._append_trace(
            current_state,
            "graph",
            "failed",
            "Patient data worker failed.",
            stage=GRAPH_PATIENT_DATA,
            error=str(exc),
        )
    return current_state


def graph_image_analysis_agent_node(service, state):
    current_state = dict(state)
    task = _current_task(current_state, GRAPH_IMAGE_ANALYSIS)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "Executing image analysis worker.",
        stage=GRAPH_IMAGE_ANALYSIS,
    )
    try:
        executor = AgentToolExecutor(service.mcp_registry, service.session_factory, current_state)
        result = executor.invoke(
            "image.analyze_uploaded_image",
            {
                "image_id": current_state.get("image_id"),
                "question": current_state.get("message"),
            },
        )
        evidence_items = [
            {
                "evidence_id": "ev:{0}".format(task.get("task_id")),
                "source_task_id": task.get("task_id"),
                "source_agent": GRAPH_IMAGE_ANALYSIS,
                "evidence_type": "image_analysis",
                "content": result,
                "source": current_state.get("image_id"),
                "confidence": 0.8,
                "risk_level": "medium",
            }
        ]
        current_state.update(_worker_success(current_state, task, result, evidence_items))
        current_state["agent_trace"] = service._append_trace(
            current_state,
            "graph",
            "completed",
            "Image analysis worker completed.",
            stage=GRAPH_IMAGE_ANALYSIS,
        )
    except (AgentToolValidationError, Exception) as exc:
        current_state.update(_worker_failure(current_state, task, exc))
        current_state["agent_trace"] = service._append_trace(
            current_state,
            "graph",
            "failed",
            "Image analysis worker failed.",
            stage=GRAPH_IMAGE_ANALYSIS,
            error=str(exc),
        )
    return current_state


def graph_medical_knowledge_agent_node(service, state):
    current_state = dict(state)
    task = _current_task(current_state, GRAPH_MEDICAL_KNOWLEDGE_AGENT)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "Executing medical knowledge worker.",
        stage=GRAPH_MEDICAL_KNOWLEDGE_AGENT,
    )
    knowledge_service = getattr(service, "medical_knowledge_service", None)
    if knowledge_service is None:
        hits = []
        retrieval_mode = "disabled"
    else:
        hits = knowledge_service.search(current_state.get("message") or "", limit=3)
        retrieval_mode = knowledge_service.retrieval_mode
    sources_text = _format_knowledge_sources(hits)
    evidence_items = [
        {
            "evidence_id": "ev:{0}:{1}".format(task.get("task_id"), index),
            "source_task_id": task.get("task_id"),
            "source_agent": GRAPH_MEDICAL_KNOWLEDGE_AGENT,
            "evidence_type": "medical_knowledge",
            "content": hit.get("content"),
            "source": hit.get("source"),
            "confidence": 0.7,
            "risk_level": "low",
        }
        for index, hit in enumerate(hits)
    ]
    current_state["knowledge_hits"] = hits
    current_state["knowledge_retrieval_mode"] = retrieval_mode
    current_state["knowledge_sources_text"] = sources_text or None
    current_state.update(_worker_success(current_state, task, {"hits": hits, "retrieval_mode": retrieval_mode}, evidence_items))
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "completed",
        "Medical knowledge worker returned {0} result(s).".format(len(hits)),
        stage=GRAPH_MEDICAL_KNOWLEDGE_AGENT,
    )
    return current_state


def graph_medical_knowledge_node(service, state):
    current_state = dict(state)
    current_state["current_task"] = current_state.get("current_task") or {
        "task_id": "medical_knowledge:adhoc",
        "agent": GRAPH_MEDICAL_KNOWLEDGE_AGENT,
        "result_key": "medical_knowledge_result",
        "required": False,
    }
    return graph_medical_knowledge_agent_node(service, current_state)


def graph_memory_agent_node(service, state):
    current_state = dict(state)
    task = _current_task(current_state, GRAPH_MEMORY)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "Executing memory worker.",
        stage=GRAPH_MEMORY,
    )
    memory_service = getattr(service, "memory_service", None)
    if memory_service is None:
        recalled = {"profiles": [], "dense_hits": [], "keyword_hits": [], "fused_hits": []}
        status = "skipped"
    else:
        try:
            recalled = memory_service.recall_long_term_memories(current_state.get("patient_id"), current_state.get("message") or "")
            status = "done"
        except Exception as exc:
            current_state.update(_worker_failure(current_state, task, exc))
            current_state["agent_trace"] = service._append_trace(
                current_state,
                "graph",
                "failed",
                "Memory worker failed.",
                stage=GRAPH_MEMORY,
                error=str(exc),
            )
            return current_state
    current_state["long_term_profile_memories"] = recalled.get("profiles") or []
    current_state["long_term_event_memories"] = recalled.get("fused_hits") or []
    evidence_items = [
        {
            "evidence_id": "ev:{0}:profile:{1}".format(task.get("task_id"), index),
            "source_task_id": task.get("task_id"),
            "source_agent": GRAPH_MEMORY,
            "evidence_type": "memory_profile",
            "content": item,
            "source": "long_term_memory",
            "confidence": 0.6,
            "risk_level": "low",
        }
        for index, item in enumerate(current_state["long_term_profile_memories"])
    ]
    current_state.update(_worker_success(current_state, task, recalled, evidence_items, status=status))
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "completed",
        "Memory worker completed.",
        stage=GRAPH_MEMORY,
    )
    return current_state


def graph_join_node(service, state):
    current_state = dict(state)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "Joining worker results.",
        stage=GRAPH_JOIN,
    )
    current_round = current_state.get("dispatch_round") or 0
    events = [event for event in current_state.get("worker_events") or [] if event.get("dispatch_round") == current_round]
    task_board = []
    for task in current_state.get("task_board") or []:
        item = dict(task)
        for event in events:
            if event.get("task_id") == item.get("task_id"):
                item["status"] = event.get("status") or item.get("status")
                if event.get("error"):
                    item["error"] = event["error"]
        task_board.append(item)
    current_state["task_board"] = task_board
    current_state["join_summary"] = summarize_task_board(task_board)
    current_state["current_task"] = None
    for event in events:
        if event.get("agent"):
            current_state["plan"] = _append_unique(current_state.get("plan") or [], event["agent"])
    current_state["plan"] = _append_unique(current_state.get("plan") or [], GRAPH_JOIN)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "completed",
        "Joined {0} worker event(s).".format(len(events)),
        stage=GRAPH_JOIN,
    )
    return current_state


def graph_gap_checker_node(service, state):
    current_state = dict(state)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "Checking task board gaps.",
        stage=GRAPH_GAP_CHECKER,
    )
    max_rounds = current_state.get("max_dispatch_rounds") or 2
    max_tasks = current_state.get("max_tasks") or 8
    max_new_tasks = current_state.get("max_new_tasks_per_round") or 2
    ready_tasks = find_ready_tasks(current_state)
    summary = current_state.get("join_summary") or summarize_task_board(current_state.get("task_board") or [])
    need_more = bool(ready_tasks)
    if summary.get("required_failed"):
        for task in current_state.get("task_board") or []:
            if task.get("status") == "failed" and task.get("required") and (task.get("retry_count") or 0) < (task.get("max_retries") or 0):
                task["status"] = "pending"
                task["retry_count"] = (task.get("retry_count") or 0) + 1
                need_more = True
    if not need_more and current_state.get("dispatch_round", 0) < max_rounds and len(current_state.get("task_board") or []) < max_tasks:
        existing_keys = {task.get("dedupe_key") or task.get("task_id") for task in current_state.get("task_board") or []}
        proposed = []
        for task in build_task_board(current_state, memory_enabled=False):
            key = task.get("dedupe_key") or task.get("task_id")
            if key not in existing_keys:
                proposed.append(task)
            if len(proposed) >= max_new_tasks:
                break
        if proposed:
            current_state["task_board"] = list(current_state.get("task_board") or []) + proposed
            current_state["proposed_tasks"] = list(current_state.get("proposed_tasks") or []) + proposed
            current_state["dispatch_round"] = (current_state.get("dispatch_round") or 0) + 1
            need_more = True
    if current_state.get("dispatch_round", 0) > max_rounds or len(current_state.get("task_board") or []) > max_tasks:
        need_more = False
    current_state["need_more_tasks"] = need_more
    current_state["plan"] = _append_unique(current_state.get("plan") or [], GRAPH_GAP_CHECKER)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "completed",
        "Gap checker will {0}.".format("continue dispatching" if need_more else "finish"),
        stage=GRAPH_GAP_CHECKER,
    )
    return current_state


def graph_composer_node(service, state):
    current_state = dict(state)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "Entering LangGraph composer node.",
        stage=GRAPH_COMPOSER,
    )
    current_state.update(service._tool_calling_node(current_state))
    sources_text = current_state.get("knowledge_sources_text") or _format_knowledge_sources(current_state.get("knowledge_hits") or [])
    current_state["knowledge_sources_text"] = sources_text or None
    final_answer = (current_state.get("final_answer") or "").strip()
    if sources_text and final_answer and sources_text not in final_answer:
        current_state["final_answer"] = "{0}\n\n{1}".format(final_answer, sources_text)
    if current_state.get("risk_flags") and current_state.get("final_answer"):
        risk_note = "提示：当前问题涉及可能较高风险的症状或场景，如症状严重或持续，请及时联系医生或急诊。"
        if risk_note not in current_state["final_answer"]:
            current_state["final_answer"] = "{0}\n\n{1}".format(current_state["final_answer"], risk_note)
    current_state["plan"] = _append_unique(current_state.get("plan") or [], GRAPH_COMPOSER)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "completed",
        "LangGraph composer node completed.",
        stage=GRAPH_COMPOSER,
    )
    return current_state


def graph_postprocess_node(service, state):
    current_state = dict(state)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "Entering LangGraph postprocess node.",
        stage=GRAPH_POSTPROCESS,
    )
    current_state.update(service._postprocess_node(current_state))
    current_state["plan"] = _append_unique(current_state.get("plan") or [], GRAPH_POSTPROCESS)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "completed",
        "LangGraph postprocess node completed.",
        stage=GRAPH_POSTPROCESS,
    )
    return current_state
