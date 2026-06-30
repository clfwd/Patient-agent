"""LangGraph node wrappers around the existing patient agent service."""

import json

from app.agent.tools import AgentToolExecutor, AgentToolValidationError
from app.tool_routing import build_heuristic_tool_selection

from .capabilities import apply_server_tool_policy, registry_for_prompt, validate_proposed_tasks, validate_task_board
from .react import build_knowledge_react_tools, build_patient_react_tools, run_bounded_react, summarize_react_result
from .router import build_risk_flags, build_task_board, find_ready_tasks, start_ready_tasks, summarize_task_board
from .schemas import PlannerOutput, ReplanDecision, WorkerEvidence
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


URGENT_RISK_PAIRS = (
    ("chest pain", "shortness of breath"),
    ("胸痛", "呼吸困难"),
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
        "task_results": {task_id: result},
        "worker_events": [
            {
                "task_id": task_id,
                "agent": task.get("agent"),
                "status": status,
                "dispatch_round": task.get("dispatch_round", state.get("dispatch_round") or 0),
                "result_key": task.get("result_key"),
            }
        ],
        "evidence_items": list(evidence_items or []),
    }


def _worker_failure(state, task, error):
    message = str(error)
    task_id = task.get("task_id")
    return {
        "task_results": {task_id: {"error": message}},
        "worker_events": [
            {
                "task_id": task_id,
                "agent": task.get("agent"),
                "status": "failed",
                "dispatch_round": task.get("dispatch_round", state.get("dispatch_round") or 0),
                "result_key": task.get("result_key"),
                "error": message,
            }
        ],
        "errors": [message],
    }


def _worker_patch(current_state, original_state, before_trace_len, before_tool_call_len, extra=None):
    patch = dict(extra or {})
    trace_delta = list(current_state.get("agent_trace") or [])[before_trace_len:]
    tool_call_delta = list(current_state.get("tool_calls") or [])[before_tool_call_len:]
    if trace_delta:
        patch["agent_trace"] = trace_delta
    if tool_call_delta:
        patch["tool_calls"] = tool_call_delta
    for key in (
        "task_results",
        "worker_events",
        "evidence_items",
        "errors",
        "patient_profile",
        "visit_search_result",
        "record_search_result",
        "image_analysis",
        "knowledge_hits",
        "knowledge_retrieval_mode",
        "knowledge_sources_text",
        "long_term_profile_memories",
        "long_term_event_memories",
        "conversation_context_summary",
        "planner_mode",
        "replanner_mode",
        "finish_reason",
        "safety_level",
        "urgent_flags",
        "answer_constraints",
        "forbidden_claims",
    ):
        if key in current_state and current_state.get(key) != original_state.get(key):
            patch[key] = current_state.get(key)
    return patch


def _tool_context(state):
    return {
        "patient_id": state.get("patient_id"),
        "patient_no": state.get("patient_no"),
        "visit_no": state.get("visit_no"),
        "image_id": state.get("image_id"),
        "metadata": state.get("metadata") or {},
    }


def _json_safe(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def _extract_json_object(text):
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("empty llm response")
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end >= start:
        raw = raw[start : end + 1]
    return json.loads(raw)


def _invoke_llm_text(service, messages):
    llm = getattr(service, "llm", None)
    if llm is None:
        return None
    if hasattr(llm, "invoke"):
        response = llm.invoke(messages)
    elif hasattr(llm, "bind_tools"):
        response = llm.bind_tools([]).invoke(messages)
    else:
        return None
    return service._stringify_content(getattr(response, "content", response))


def _conversation_summary(state):
    history = state.get("conversation_history") or []
    active_topics = []
    if history:
        active_topics = [item.get("content", "")[:120] for item in history[-4:] if item.get("content")]
    return {
        "active_topics": active_topics,
        "current_message": state.get("message") or "",
        "has_image": bool(state.get("image_id")),
    }


def _planner_prompt(state):
    return [
        {
            "role": "system",
            "content": (
                "You are PlannerAgent for a bounded medical assistant graph. "
                "Return JSON only with keys: tasks, risk_flags, conversation_context_summary, planning_notes. "
                "Tasks must use only agents/tools from the capability registry. "
                "Do not create tool calls; only describe task intent."
            ),
        },
        {
            "role": "user",
            "content": _json_safe(
                {
                    "message": state.get("message") or "",
                    "conversation_history": state.get("conversation_history") or [],
                    "verified_patient": state.get("verified_patient") or {},
                    "image_context": state.get("image_context") or {},
                    "capability_registry": registry_for_prompt(),
                    "max_tasks": state.get("max_tasks") or 8,
                }
            ),
        },
    ]


def _run_llm_planner(service, state):
    text = _invoke_llm_text(service, _planner_prompt(state))
    payload = _extract_json_object(text)
    output = PlannerOutput.parse_obj(payload)
    tasks = validate_task_board([task.dict() for task in output.tasks], max_tasks=state.get("max_tasks") or 8)
    if not tasks:
        raise ValueError("planner produced no valid tasks")
    return output, tasks


def _rule_planner_output(state, service):
    tasks = build_task_board(state, memory_enabled=getattr(service, "memory_service", None) is not None)
    return {
        "task_board": tasks,
        "risk_flags": build_risk_flags(state),
        "conversation_context_summary": _conversation_summary(state),
    }


def _safety_signals(state):
    message = (state.get("message") or "").lower()
    urgent = []
    for left, right in URGENT_RISK_PAIRS:
        if left.lower() in message and right.lower() in message:
            urgent.extend([left, right])
    risk_flags = list(state.get("risk_flags") or [])
    for flag in build_risk_flags(state):
        if flag not in risk_flags:
            risk_flags.append(flag)
    safety_level = "urgent" if urgent else ("caution" if risk_flags else "normal")
    answer_constraints = list(state.get("answer_constraints") or [])
    forbidden_claims = list(state.get("forbidden_claims") or [])
    if safety_level == "urgent":
        answer_constraints = _append_unique(answer_constraints, "Recommend urgent medical care before general explanation.")
        answer_constraints = _append_unique(answer_constraints, "Do not suggest self-observation as a substitute for urgent care.")
        forbidden_claims = _append_unique(forbidden_claims, "Do not provide a definitive diagnosis.")
    elif safety_level == "caution":
        answer_constraints = _append_unique(answer_constraints, "Explain uncertainty and recommend clinician follow-up when symptoms persist.")
    return {
        "risk_flags": risk_flags,
        "safety_level": safety_level,
        "urgent_flags": urgent,
        "answer_constraints": answer_constraints,
        "forbidden_claims": forbidden_claims,
    }


def _evidence_dict(task, agent_name, source_type, content, source_id=None, source_title=None, confidence=0.7, patient_specific=False, medical_knowledge=False, limitations=None):
    evidence = WorkerEvidence(
        evidence_id="ev:{0}:{1}".format(task.get("task_id"), source_type),
        task_id=task.get("task_id"),
        agent_name=agent_name,
        source_type=source_type,
        source_id=source_id,
        source_title=source_title,
        content_summary=content,
        raw_excerpt=content,
        confidence=confidence,
        patient_specific=patient_specific,
        medical_knowledge=medical_knowledge,
        limitations=list(limitations or []),
    )
    return evidence.dict()


def _filter_tools(tools, allowed_tools):
    allowed = set(allowed_tools or [])
    return [tool for tool in tools if getattr(tool, "name", None) in allowed]


def _patient_fallback_tool_plan(state, task):
    message = (state.get("message") or "").lower()
    goal = (task.get("goal") or "").lower()
    text = "{0} {1}".format(message, goal)
    plan = []
    if any(keyword in text for keyword in ("visit", "latest", "recent", "就诊", "最近")):
        plan.append(("visit.search_visits", {"limit": 1, "sort_by": "visit_time", "sort_order": "desc"}))
    if any(keyword in text for keyword in ("record", "medical", "diagnosis", "blood pressure", "血压", "病历", "诊断")):
        plan.append(("medical_record.search_records", {"limit": 3, "sort_by": "record_date", "sort_order": "desc"}))
    if any(keyword in text for keyword in ("profile", "patient", "资料", "个人信息")) or not plan:
        plan.append(("patient.get_patient_profile", {}))
    allowed = set(task.get("effective_allowed_tools") or task.get("allowed_tools") or [])
    return [(name, args) for name, args in plan if name in allowed]


def _replanner_prompt(state):
    return [
        {
            "role": "system",
            "content": (
                "You are ReplannerAgent for a bounded medical assistant graph. "
                "Return JSON only matching ReplanDecision. Decide finish, continue, or force_finish. "
                "Only propose incremental tasks from the capability registry. "
                "Set safety_level and answer_constraints for urgent medical risk."
            ),
        },
        {
            "role": "user",
            "content": _json_safe(
                {
                    "message": state.get("message") or "",
                    "conversation_context_summary": state.get("conversation_context_summary") or {},
                    "task_board": state.get("task_board") or [],
                    "worker_events": state.get("worker_events") or [],
                    "task_results": state.get("task_results") or {},
                    "evidence_items": state.get("evidence_items") or [],
                    "risk_flags": state.get("risk_flags") or [],
                    "join_summary": state.get("join_summary") or {},
                    "budgets": {
                        "dispatch_round": state.get("dispatch_round") or 0,
                        "max_dispatch_rounds": state.get("max_dispatch_rounds") or 2,
                        "max_tasks": state.get("max_tasks") or 8,
                        "max_new_tasks_per_round": state.get("max_new_tasks_per_round") or 2,
                    },
                    "capability_registry": registry_for_prompt(),
                }
            ),
        },
    ]


def _run_llm_replanner(service, state):
    text = _invoke_llm_text(service, _replanner_prompt(state))
    payload = _extract_json_object(text)
    decision = ReplanDecision.parse_obj(payload)
    proposed, rejected = validate_proposed_tasks(
        [task.dict() for task in decision.proposed_tasks],
        existing_tasks=state.get("task_board") or [],
        max_tasks=state.get("max_new_tasks_per_round") or 2,
    )
    return decision, proposed, rejected


def _rule_replan_decision(state):
    max_rounds = state.get("max_dispatch_rounds") or 2
    max_tasks = state.get("max_tasks") or 8
    ready_tasks = find_ready_tasks(state)
    summary = state.get("join_summary") or summarize_task_board(state.get("task_board") or [])
    safety = _safety_signals(state)
    if (state.get("dispatch_round") or 0) >= max_rounds:
        return {
            "decision": "force_finish",
            "finish_reason": "max_rounds_reached",
            "need_more_tasks": False,
            "proposed_tasks": [],
            **safety,
        }
    if len(state.get("task_board") or []) >= max_tasks:
        return {
            "decision": "force_finish",
            "finish_reason": "max_tasks_reached",
            "need_more_tasks": False,
            "proposed_tasks": [],
            **safety,
        }
    if summary.get("required_failed"):
        return {
            "decision": "continue",
            "finish_reason": "unrecoverable_required_task_failed",
            "need_more_tasks": True,
            "proposed_tasks": [],
            **safety,
        }
    if ready_tasks:
        return {
            "decision": "continue",
            "finish_reason": "degraded_answer_allowed",
            "need_more_tasks": True,
            "proposed_tasks": [],
            **safety,
        }
    return {
        "decision": "finish",
        "finish_reason": "evidence_sufficient",
        "need_more_tasks": False,
        "proposed_tasks": [],
        **safety,
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
        "PlannerAgent is building a bounded task board.",
        stage=GRAPH_PLANNER,
    )
    planner_mode = "llm"
    fallback_reason = None
    try:
        planner_output, task_board = _run_llm_planner(service, current_state)
        risk_flags = list(planner_output.risk_flags or [])
        current_state["conversation_context_summary"] = planner_output.conversation_context_summary or _conversation_summary(current_state)
    except Exception as exc:
        planner_mode = "rule_fallback"
        fallback_reason = str(exc)
        rule_output = _rule_planner_output(current_state, service)
        task_board = rule_output["task_board"]
        risk_flags = rule_output["risk_flags"]
        current_state["conversation_context_summary"] = rule_output["conversation_context_summary"]
    safety = _safety_signals(dict(current_state, risk_flags=risk_flags))
    current_state["task_board"] = task_board
    current_state["risk_flags"] = list(current_state.get("risk_flags") or [])
    for flag in safety["risk_flags"]:
        current_state["risk_flags"] = _append_unique(current_state["risk_flags"], flag)
    current_state["safety_level"] = safety["safety_level"]
    current_state["urgent_flags"] = safety["urgent_flags"]
    current_state["answer_constraints"] = safety["answer_constraints"]
    current_state["forbidden_claims"] = safety["forbidden_claims"]
    current_state["planner_mode"] = planner_mode
    current_state["plan"] = _append_unique(current_state.get("plan") or [], GRAPH_PLANNER)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "completed",
        "PlannerAgent created {0} task(s) using {1}.".format(len(task_board), planner_mode),
        stage=GRAPH_PLANNER,
        planner_mode=planner_mode,
        fallback_reason=fallback_reason,
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
        "Selecting ready tasks for parallel dispatch.",
        stage=GRAPH_DISPATCHER,
    )
    tasks, task_board = start_ready_tasks(current_state)
    current_state["task_board"] = task_board
    current_state["current_task"] = None
    current_state["dispatched_tasks"] = tasks
    current_state["plan"] = _append_unique(current_state.get("plan") or [], GRAPH_DISPATCHER)
    if tasks:
        detail = "Dispatching {0} ready task(s).".format(len(tasks))
    else:
        detail = "No ready task found."
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
    before_trace_len = len(current_state.get("agent_trace") or [])
    before_tool_call_len = len(current_state.get("tool_calls") or [])
    task = _current_task(current_state, GRAPH_PATIENT_DATA)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "Executing bounded PatientDataAgent.",
        stage=GRAPH_PATIENT_DATA,
    )
    try:
        task = apply_server_tool_policy(task) or task
        executor = AgentToolExecutor(service.mcp_registry, service.session_factory, current_state)
        react_summary = None
        react_error = None
        try:
            tools = build_patient_react_tools(service, current_state, task.get("effective_allowed_tools") or [])
            result = run_bounded_react(
                service,
                current_state,
                task,
                tools,
                (
                    "You are PatientDataAgent. Use only injected patient data tools. "
                    "Retrieve verified-patient facts. Do not diagnose, interpret images, or use non-patient tools. "
                    "Never invent patient_id or patient_no; trusted context is injected by the executor."
                ),
            )
            if result:
                react_summary = summarize_react_result(result.get("messages") if isinstance(result, dict) else [])
        except Exception as exc:
            react_error = str(exc)

        executed = []
        if not react_summary or not (react_summary.get("tool_results") or current_state.get("tool_calls")):
            for tool_name, arguments in _patient_fallback_tool_plan(current_state, task):
                executed.append({"tool_name": tool_name, "result": executor.invoke(tool_name, arguments)})

        result_payload = {
            "mode": "bounded_react" if react_summary and not executed else "bounded_rule_fallback",
            "react_summary": react_summary,
            "executed": executed,
            "react_error": react_error,
        }
        evidence_items = [
            _evidence_dict(
                task,
                GRAPH_PATIENT_DATA,
                "patient_data",
                result_payload,
                source_id=tool.get("tool_name"),
                source_title="Patient data tool output",
                confidence=1.0,
                patient_specific=True,
                limitations=["PatientDataAgent retrieves facts only and does not provide diagnosis."],
            )
            for tool in (executed or [{"tool_name": "patient_data_react"}])
        ]
        current_state.update(_worker_success(current_state, task, result_payload, evidence_items))
        current_state["agent_trace"] = service._append_trace(
            current_state,
            "graph",
            "completed",
            "PatientDataAgent completed.",
            stage=GRAPH_PATIENT_DATA,
            worker_mode=result_payload["mode"],
            react_error=react_error,
        )
        return _worker_patch(current_state, state, before_trace_len, before_tool_call_len)
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
        return _worker_patch(current_state, state, before_trace_len, before_tool_call_len)


def graph_image_analysis_agent_node(service, state):
    current_state = dict(state)
    before_trace_len = len(current_state.get("agent_trace") or [])
    before_tool_call_len = len(current_state.get("tool_calls") or [])
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
            _evidence_dict(
                task,
                GRAPH_IMAGE_ANALYSIS,
                "image_analysis",
                result,
                source_id=current_state.get("image_id"),
                source_title="Uploaded image analysis",
                confidence=0.8,
                patient_specific=True,
                limitations=["Image analysis is limited to visible content and uploaded image quality."],
            )
        ]
        current_state.update(_worker_success(current_state, task, result, evidence_items))
        current_state["agent_trace"] = service._append_trace(
            current_state,
            "graph",
            "completed",
            "Image analysis worker completed.",
            stage=GRAPH_IMAGE_ANALYSIS,
        )
        return _worker_patch(current_state, state, before_trace_len, before_tool_call_len)
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
        return _worker_patch(current_state, state, before_trace_len, before_tool_call_len)


def graph_medical_knowledge_agent_node(service, state):
    current_state = dict(state)
    before_trace_len = len(current_state.get("agent_trace") or [])
    before_tool_call_len = len(current_state.get("tool_calls") or [])
    task = _current_task(current_state, GRAPH_MEDICAL_KNOWLEDGE_AGENT)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "Executing bounded MedicalKnowledgeAgent.",
        stage=GRAPH_MEDICAL_KNOWLEDGE_AGENT,
    )
    task = apply_server_tool_policy(task) or task
    knowledge_service = getattr(service, "medical_knowledge_service", None)
    react_summary = None
    react_error = None
    deep_result = None
    if knowledge_service is not None:
        try:
            tools = _filter_tools(build_knowledge_react_tools(service, current_state), task.get("effective_allowed_tools") or [])
            result = run_bounded_react(
                service,
                current_state,
                task,
                tools,
                (
                    "You are MedicalKnowledgeAgent. Use only medical_knowledge.search or "
                    "medical_knowledge.deep_retrieve. Simple questions should use search once. "
                    "Complex indicator or multi-symptom questions should use deep_retrieve once. "
                    "Return a concise knowledge summary with sources and limitations. Do not diagnose."
                ),
            )
            if result:
                react_summary = summarize_react_result(result.get("messages") if isinstance(result, dict) else [])
        except Exception as exc:
            react_error = str(exc)

    if knowledge_service is None:
        hits = []
        retrieval_mode = "disabled"
    elif react_summary and current_state.get("tool_calls"):
        retrieval_mode = "bounded_react"
        last_result = current_state.get("tool_calls")[-1].get("result")
        if isinstance(last_result, dict) and "hits" in last_result:
            deep_result = last_result
            hits = deep_result.get("hits") or []
        elif isinstance(last_result, list):
            hits = last_result
        else:
            hits = []
    else:
        message = current_state.get("message") or ""
        if "blood pressure" in message.lower() or "chest pain" in message.lower() or "shortness of breath" in message.lower() or "血压" in message or "胸痛" in message:
            deep_result = knowledge_service.deep_retrieve(message, limit=5)
            hits = deep_result.get("hits") or []
            retrieval_mode = deep_result.get("retrieval_mode") or "deep_keyword_rrf"
            current_state["tool_calls"] = list(current_state.get("tool_calls") or []) + [
                {
                    "tool_name": "medical_knowledge.deep_retrieve",
                    "arguments": {"query": message, "limit": 5},
                    "ok": True,
                    "result": deep_result,
                    "error": None,
                }
            ]
        else:
            hits = knowledge_service.search(message, limit=3)
            retrieval_mode = knowledge_service.retrieval_mode
            current_state["tool_calls"] = list(current_state.get("tool_calls") or []) + [
                {
                    "tool_name": "medical_knowledge.search",
                    "arguments": {"query": message, "limit": 3},
                    "ok": True,
                    "result": {"hits": hits},
                    "error": None,
                }
            ]
    sources_text = _format_knowledge_sources(hits)
    evidence_items = [
        _evidence_dict(
            task,
            GRAPH_MEDICAL_KNOWLEDGE_AGENT,
            "medical_knowledge",
            hit.get("content"),
            source_id=hit.get("chunk_id"),
            source_title=hit.get("title"),
            confidence=0.7,
            medical_knowledge=True,
            limitations=["General medical knowledge; not a patient-specific diagnosis."],
        )
        for index, hit in enumerate(hits)
    ]
    current_state["knowledge_hits"] = hits
    current_state["knowledge_retrieval_mode"] = retrieval_mode
    current_state["knowledge_sources_text"] = sources_text or None
    current_state.update(
        _worker_success(
            current_state,
            task,
            {
                "hits": hits,
                "retrieval_mode": retrieval_mode,
                "react_summary": react_summary,
                "deep_result": deep_result,
                "react_error": react_error,
            },
            evidence_items,
        )
    )
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "completed",
        "MedicalKnowledgeAgent returned {0} result(s).".format(len(hits)),
        stage=GRAPH_MEDICAL_KNOWLEDGE_AGENT,
        worker_mode=retrieval_mode,
        react_error=react_error,
    )
    return _worker_patch(current_state, state, before_trace_len, before_tool_call_len)


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
    before_trace_len = len(current_state.get("agent_trace") or [])
    before_tool_call_len = len(current_state.get("tool_calls") or [])
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
            return _worker_patch(current_state, state, before_trace_len, before_tool_call_len)
    current_state["long_term_profile_memories"] = recalled.get("profiles") or []
    current_state["long_term_event_memories"] = recalled.get("fused_hits") or []
    evidence_items = [
        _evidence_dict(
            task,
            GRAPH_MEMORY,
            "memory",
            item,
            source_id="long_term_memory",
            source_title="Long-term memory",
            confidence=0.6,
            patient_specific=True,
            limitations=["Long-term memory is historical context, not current clinical fact."],
        )
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
    return _worker_patch(current_state, state, before_trace_len, before_tool_call_len)


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
    task_ids = {task.get("task_id") for task in current_state.get("task_board") or []}
    discarded_events = [
        event
        for event in current_state.get("worker_events") or []
        if event.get("dispatch_round") == current_round and event.get("task_id") not in task_ids
    ]
    events = [
        event
        for event in current_state.get("worker_events") or []
        if event.get("dispatch_round") == current_round and event.get("task_id") in task_ids
    ]
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
        discarded_events=len(discarded_events),
    )
    return current_state


def graph_gap_checker_node(service, state):
    current_state = dict(state)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "started",
        "ReplannerAgent is checking evidence gaps.",
        stage=GRAPH_GAP_CHECKER,
    )
    max_rounds = current_state.get("max_dispatch_rounds") or 2
    max_tasks = current_state.get("max_tasks") or 8
    max_new_tasks = current_state.get("max_new_tasks_per_round") or 2
    summary = current_state.get("join_summary") or summarize_task_board(current_state.get("task_board") or [])
    replanner_mode = "llm"
    fallback_reason = None
    decision_payload = None
    proposed = []
    rejected_task_reasons = []
    try:
        decision, proposed, rejected_task_reasons = _run_llm_replanner(service, current_state)
        decision_payload = decision.dict()
    except Exception as exc:
        replanner_mode = "rule_fallback"
        fallback_reason = str(exc)
        decision_payload = _rule_replan_decision(current_state)
        proposed = decision_payload.get("proposed_tasks") or []

    need_more = decision_payload.get("decision") == "continue"
    accepted_proposed_tasks = 0
    retried_required_tasks = 0
    force_finish_reason = None
    if summary.get("required_failed"):
        for task in current_state.get("task_board") or []:
            if task.get("status") == "failed" and task.get("required") and (task.get("retry_count") or 0) < (task.get("max_retries") or 0):
                task["status"] = "pending"
                task["retry_count"] = (task.get("retry_count") or 0) + 1
                retried_required_tasks += 1
                need_more = True
    if need_more and proposed and current_state.get("dispatch_round", 0) < max_rounds and len(current_state.get("task_board") or []) < max_tasks:
        existing_keys = {task.get("dedupe_key") or task.get("task_id") for task in current_state.get("task_board") or []}
        accepted = []
        for task in proposed:
            key = task.get("dedupe_key") or task.get("task_id")
            if key not in existing_keys:
                accepted.append(task)
                existing_keys.add(key)
            if len(accepted) >= max_new_tasks:
                break
        if accepted:
            current_state["task_board"] = list(current_state.get("task_board") or []) + accepted
            current_state["proposed_tasks"] = list(current_state.get("proposed_tasks") or []) + accepted
            current_state["dispatch_round"] = (current_state.get("dispatch_round") or 0) + 1
            accepted_proposed_tasks = len(accepted)
    if not need_more and current_state.get("dispatch_round", 0) < max_rounds and len(current_state.get("task_board") or []) < max_tasks:
        existing_keys = {task.get("dedupe_key") or task.get("task_id") for task in current_state.get("task_board") or []}
        rule_proposed = []
        for task in proposed or build_task_board(current_state, memory_enabled=False):
            key = task.get("dedupe_key") or task.get("task_id")
            if key not in existing_keys:
                rule_proposed.append(task)
            if len(rule_proposed) >= max_new_tasks:
                break
        if rule_proposed and decision_payload.get("decision") == "continue":
            current_state["task_board"] = list(current_state.get("task_board") or []) + rule_proposed
            current_state["proposed_tasks"] = list(current_state.get("proposed_tasks") or []) + rule_proposed
            current_state["dispatch_round"] = (current_state.get("dispatch_round") or 0) + 1
            accepted_proposed_tasks = len(rule_proposed)
            need_more = True
    if current_state.get("dispatch_round", 0) >= max_rounds and need_more:
        decision_payload["decision"] = "force_finish"
        decision_payload["finish_reason"] = "max_rounds_reached"
        need_more = False
    if current_state.get("dispatch_round", 0) > max_rounds or len(current_state.get("task_board") or []) > max_tasks:
        decision_payload["decision"] = "force_finish"
        decision_payload["finish_reason"] = "max_tasks_reached"
        need_more = False
    if need_more and not find_ready_tasks(current_state) and accepted_proposed_tasks == 0 and retried_required_tasks == 0:
        decision_payload["decision"] = "force_finish"
        decision_payload["finish_reason"] = "degraded_answer_allowed"
        need_more = False
        force_finish_reason = "continue_without_ready_or_accepted_tasks"
    current_state["need_more_tasks"] = need_more
    current_state["accepted_proposed_tasks"] = accepted_proposed_tasks
    current_state["rejected_proposed_tasks"] = len(rejected_task_reasons)
    current_state["rejected_task_reasons"] = rejected_task_reasons
    current_state["replanner_mode"] = replanner_mode
    current_state["finish_reason"] = decision_payload.get("finish_reason")
    current_state["safety_level"] = decision_payload.get("safety_level") or current_state.get("safety_level") or "normal"
    current_state["urgent_flags"] = decision_payload.get("urgent_flags") or current_state.get("urgent_flags") or []
    current_state["answer_constraints"] = decision_payload.get("answer_constraints") or current_state.get("answer_constraints") or []
    current_state["forbidden_claims"] = decision_payload.get("forbidden_claims") or current_state.get("forbidden_claims") or []
    current_state["plan"] = _append_unique(current_state.get("plan") or [], GRAPH_GAP_CHECKER)
    current_state["agent_trace"] = service._append_trace(
        current_state,
        "graph",
        "completed",
        "ReplannerAgent decision: {0}.".format(decision_payload.get("decision")),
        stage=GRAPH_GAP_CHECKER,
        replanner_mode=replanner_mode,
        finish_reason=current_state.get("finish_reason"),
        accepted_proposed_tasks=accepted_proposed_tasks,
        rejected_proposed_tasks=len(rejected_task_reasons),
        rejected_task_reasons=rejected_task_reasons,
        force_finish_reason=force_finish_reason,
        fallback_reason=fallback_reason,
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
    has_worker_output = bool(current_state.get("task_results") or current_state.get("evidence_items") or current_state.get("tool_calls"))
    if has_worker_output:
        current_state["final_answer"] = (current_state.get("final_answer") or "").strip() or service._build_fallback_answer(current_state)
        current_state["tool_calling_mode"] = current_state.get("tool_calling_mode") or "graph-workers"
    else:
        current_state.update(service._tool_calling_node(current_state))
    sources_text = current_state.get("knowledge_sources_text") or _format_knowledge_sources(current_state.get("knowledge_hits") or [])
    current_state["knowledge_sources_text"] = sources_text or None
    final_answer = (current_state.get("final_answer") or "").strip()
    if sources_text and final_answer and sources_text not in final_answer:
        current_state["final_answer"] = "{0}\n\n{1}".format(final_answer, sources_text)
    if current_state.get("finish_reason") and current_state.get("finish_reason") != "evidence_sufficient" and current_state.get("final_answer"):
        degraded_note = "Note: some requested evidence was unavailable or the graph budget was exhausted, so this answer is limited to retrieved evidence."
        if degraded_note not in current_state["final_answer"]:
            current_state["final_answer"] = "{0}\n\n{1}".format(current_state["final_answer"], degraded_note)
    if current_state.get("safety_level") == "urgent" and current_state.get("final_answer"):
        urgent_note = "Urgent safety note: chest pain with breathing difficulty can be serious. Seek urgent medical care or emergency services promptly; do not rely on this assistant for diagnosis."
        if urgent_note not in current_state["final_answer"]:
            current_state["final_answer"] = "{0}\n\n{1}".format(urgent_note, current_state["final_answer"])
    for constraint in current_state.get("answer_constraints") or []:
        current_state["agent_trace"] = service._append_trace(
            current_state,
            "safety",
            "constraint",
            constraint,
            stage=GRAPH_COMPOSER,
        )
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
