import json
import unittest

from langgraph.types import Send

import app.agent.graph.react as react_module
from app.agent.graph.capabilities import (
    TaskBoardValidationError,
    apply_server_tool_policy,
    normalize_planned_tasks,
    normalize_proposed_tasks,
    validate_proposed_tasks,
    validate_task_board,
)
from app.agent.graph.nodes import graph_composer_node, graph_gap_checker_node, graph_planner_node
from app.agent.graph.react import run_bounded_react, wrap_tools_with_budget, ToolCallBudget
from app.agent.graph.router import (
    build_risk_flags,
    build_task_board,
    find_ready_tasks,
    route_after_dispatcher,
    start_next_ready_task,
    start_ready_tasks,
)
from app.agent.graph.state import GRAPH_IMAGE_ANALYSIS, GRAPH_MEDICAL_KNOWLEDGE_AGENT, GRAPH_MEMORY, GRAPH_PATIENT_DATA

try:
    from langchain_core.messages import AIMessage
    from langchain_core.tools import StructuredTool
except ImportError:  # pragma: no cover
    AIMessage = None
    StructuredTool = None


class FakeComposerService(object):
    def _append_trace(self, state, event, status, detail, stage=None, **extra):
        trace = list(state.get("agent_trace") or [])
        item = {"event": event, "status": status, "detail": detail, "stage": stage}
        item.update(extra)
        trace.append(item)
        return trace

    def _build_fallback_answer(self, state):
        return "Composed from worker results."

    def _tool_calling_node(self, state):
        raise AssertionError("Composer should not execute tool-calling when worker output exists.")


class FakeGraphService(FakeComposerService):
    llm = None

    def _stringify_content(self, content):
        if isinstance(content, str):
            return content
        return str(content)


class FakeLLMResponse(object):
    def __init__(self, content):
        self.content = content


class FakeJsonLLM(object):
    def __init__(self, payload):
        self.payload = payload

    def invoke(self, messages):
        return FakeLLMResponse(json.dumps(self.payload))


class FakeLLMGraphService(FakeGraphService):
    def __init__(self, payload):
        self.llm = FakeJsonLLM(payload)


class FakeStructuredRunnable(object):
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error

    def invoke(self, messages):
        if self.error:
            raise self.error
        return self.payload


class FakeStructuredLLM(object):
    def __init__(self, structured_payload=None, fallback_payload=None, structured_error=None):
        self.structured_payload = structured_payload
        self.fallback_payload = fallback_payload
        self.structured_error = structured_error
        self.structured_invocations = 0
        self.json_invocations = 0
        self.structured_schema = None

    def with_structured_output(self, schema):
        self.structured_schema = schema
        self.structured_invocations += 1
        return FakeStructuredRunnable(self.structured_payload, self.structured_error)

    def invoke(self, messages):
        self.json_invocations += 1
        return FakeLLMResponse(json.dumps(self.fallback_payload))


class FakeStructuredGraphService(FakeGraphService):
    def __init__(self, structured_payload=None, fallback_payload=None, structured_error=None):
        self.llm = FakeStructuredLLM(
            structured_payload=structured_payload,
            fallback_payload=fallback_payload,
            structured_error=structured_error,
        )


def _valid_patient_task(task_id="patient_data:1", status="pending", dedupe_key="patient_data:structured_context", depends_on=None):
    return apply_server_tool_policy(
        {
            "task_id": task_id,
            "agent": GRAPH_PATIENT_DATA,
            "goal": "Retrieve patient data.",
            "status": status,
            "depends_on": list(depends_on or []),
            "result_key": "patient_data_result",
            "priority": 90,
            "required": True,
            "dedupe_key": dedupe_key,
            "created_by": "graph_planner",
            "parent_task_id": None,
            "retry_count": 0,
            "max_retries": 1,
            "timeout_seconds": 20,
            "reason": "test",
            "allowed_tools": ["patient.get_patient_profile"],
            "expected_evidence": ["patient profile"],
            "max_tool_steps": 2,
        }
    )


def _valid_knowledge_task(task_id="medical_knowledge:1", status="pending", dedupe_key="medical_knowledge:query", depends_on=None):
    return apply_server_tool_policy(
        {
            "task_id": task_id,
            "agent": GRAPH_MEDICAL_KNOWLEDGE_AGENT,
            "goal": "Retrieve medical knowledge.",
            "status": status,
            "depends_on": list(depends_on or []),
            "result_key": "medical_knowledge_result",
            "priority": 80,
            "required": False,
            "dedupe_key": dedupe_key,
            "created_by": "graph_planner",
            "parent_task_id": None,
            "retry_count": 0,
            "max_retries": 1,
            "timeout_seconds": 20,
            "reason": "test",
            "allowed_tools": ["medical_knowledge.search"],
            "expected_evidence": ["medical knowledge"],
            "max_tool_steps": 1,
        }
    )


def _continue_payload(proposed_tasks=None):
    return {
        "decision": "continue",
        "finish_reason": "degraded_answer_allowed",
        "missing_evidence": ["patient data"],
        "proposed_tasks": proposed_tasks or [],
        "stop_reason": "need more evidence",
        "confidence": 0.5,
    }


def _semantic_patient_task(dedupe_key="patient_data:structured_context", depends_on_dedupe_keys=None):
    return {
        "agent": GRAPH_PATIENT_DATA,
        "task_type": "patient_data_lookup",
        "dedupe_key": dedupe_key,
        "depends_on_dedupe_keys": list(depends_on_dedupe_keys or []),
        "goal": "Retrieve patient data.",
        "reason": "test",
        "result_key": "patient_data_result",
        "allowed_tools": ["patient.get_patient_profile"],
        "expected_evidence": ["patient profile"],
        "priority": 90,
        "required": True,
        "max_tool_steps": 2,
    }


def _semantic_knowledge_task(dedupe_key="medical_knowledge:query", depends_on_dedupe_keys=None):
    return {
        "agent": GRAPH_MEDICAL_KNOWLEDGE_AGENT,
        "task_type": "medical_knowledge_lookup",
        "dedupe_key": dedupe_key,
        "depends_on_dedupe_keys": list(depends_on_dedupe_keys or []),
        "goal": "Retrieve medical knowledge.",
        "reason": "test",
        "result_key": "medical_knowledge_result",
        "allowed_tools": ["medical_knowledge.search"],
        "expected_evidence": ["medical knowledge"],
        "priority": 80,
        "required": False,
        "max_tool_steps": 1,
    }


class LangGraphTaskBoardTest(unittest.TestCase):
    def test_planner_builds_medical_knowledge_and_memory_tasks(self):
        state = {
            "message": "What is blood sugar?",
            "patient_id": "patient-1",
        }

        tasks = build_task_board(state, memory_enabled=True)
        agents = {task["agent"] for task in tasks}

        self.assertIn(GRAPH_MEMORY, agents)
        self.assertIn(GRAPH_MEDICAL_KNOWLEDGE_AGENT, agents)

    def test_planner_routes_patient_data_and_image_tasks(self):
        state = {
            "message": "Summarize my latest visit and this image.",
            "patient_id": "patient-1",
            "image_id": "image-1",
        }

        tasks = build_task_board(state, memory_enabled=False)
        agents = {task["agent"] for task in tasks}

        self.assertIn(GRAPH_PATIENT_DATA, agents)
        self.assertIn(GRAPH_IMAGE_ANALYSIS, agents)

    def test_dispatcher_selects_highest_priority_ready_task(self):
        state = {
            "task_board": [
                {"task_id": "low", "agent": GRAPH_MEDICAL_KNOWLEDGE_AGENT, "status": "pending", "depends_on": [], "priority": 10},
                {"task_id": "high", "agent": GRAPH_PATIENT_DATA, "status": "pending", "depends_on": [], "priority": 90},
            ]
        }

        task, task_board = start_next_ready_task(state)

        self.assertEqual(task["task_id"], "high")
        statuses = {item["task_id"]: item["status"] for item in task_board}
        self.assertEqual(statuses["high"], "running")
        self.assertEqual(statuses["low"], "pending")

    def test_dispatcher_starts_multiple_ready_tasks(self):
        state = {
            "dispatch_round": 0,
            "max_parallel_tasks": 4,
            "task_board": [
                {"task_id": "patient", "agent": GRAPH_PATIENT_DATA, "status": "pending", "depends_on": [], "priority": 90},
                {"task_id": "image", "agent": GRAPH_IMAGE_ANALYSIS, "status": "pending", "depends_on": [], "priority": 85},
                {"task_id": "knowledge", "agent": GRAPH_MEDICAL_KNOWLEDGE_AGENT, "status": "pending", "depends_on": [], "priority": 80},
            ],
        }

        tasks, task_board = start_ready_tasks(state)

        self.assertEqual([task["task_id"] for task in tasks], ["patient", "image", "knowledge"])
        statuses = {item["task_id"]: item["status"] for item in task_board}
        self.assertEqual(statuses, {"patient": "running", "image": "running", "knowledge": "running"})
        self.assertEqual({task["dispatch_round"] for task in tasks}, {0})

    def test_dispatcher_respects_max_parallel_tasks(self):
        state = {
            "max_parallel_tasks": 2,
            "task_board": [
                {"task_id": "patient", "agent": GRAPH_PATIENT_DATA, "status": "pending", "depends_on": [], "priority": 90},
                {"task_id": "image", "agent": GRAPH_IMAGE_ANALYSIS, "status": "pending", "depends_on": [], "priority": 85},
                {"task_id": "knowledge", "agent": GRAPH_MEDICAL_KNOWLEDGE_AGENT, "status": "pending", "depends_on": [], "priority": 80},
            ],
        }

        tasks, task_board = start_ready_tasks(state)

        self.assertEqual([task["task_id"] for task in tasks], ["patient", "image"])
        statuses = {item["task_id"]: item["status"] for item in task_board}
        self.assertEqual(statuses["patient"], "running")
        self.assertEqual(statuses["image"], "running")
        self.assertEqual(statuses["knowledge"], "pending")

    def test_route_after_dispatcher_returns_send_per_dispatched_task(self):
        state = {
            "message": "test",
            "dispatched_tasks": [
                {"task_id": "patient", "agent": GRAPH_PATIENT_DATA, "status": "running"},
                {"task_id": "image", "agent": GRAPH_IMAGE_ANALYSIS, "status": "running"},
            ],
        }

        sends = route_after_dispatcher(state)

        self.assertEqual(len(sends), 2)
        self.assertTrue(all(isinstance(item, Send) for item in sends))
        self.assertEqual([item.node for item in sends], [GRAPH_PATIENT_DATA, GRAPH_IMAGE_ANALYSIS])
        self.assertEqual([item.arg["current_task"]["task_id"] for item in sends], ["patient", "image"])

    def test_composer_uses_worker_results_without_repeating_tool_calling(self):
        state = {
            "task_results": {"image": {"analysis": {"reasoning": "already done"}}},
            "evidence_items": [{"evidence_type": "image_analysis"}],
            "tool_calls": [{"tool_name": "image.analyze_uploaded_image"}],
            "agent_trace": [],
            "plan": [],
        }

        result = graph_composer_node(FakeComposerService(), state)

        self.assertEqual(result["final_answer"], "Composed from worker results.")
        self.assertEqual(result["tool_calling_mode"], "graph-workers")
        self.assertIn("graph_composer", result["plan"])

    def test_dispatcher_respects_dependencies(self):
        state = {
            "task_board": [
                {"task_id": "base", "agent": GRAPH_PATIENT_DATA, "status": "pending", "depends_on": [], "priority": 50},
                {"task_id": "dependent", "agent": GRAPH_MEDICAL_KNOWLEDGE_AGENT, "status": "pending", "depends_on": ["base"], "priority": 90},
            ]
        }

        ready = find_ready_tasks(state)

        self.assertEqual([task["task_id"] for task in ready], ["base"])

    def test_risk_keywords_are_detected(self):
        self.assertIn("chest pain", build_risk_flags({"message": "I have chest pain and dizziness."}))

    def test_capability_policy_intersects_allowed_tools_and_caps_steps(self):
        task = {
            "task_id": "patient_data:bad-tools",
            "agent": GRAPH_PATIENT_DATA,
            "goal": "Retrieve patient facts.",
            "result_key": "patient_data_result",
            "priority": 90,
            "required": True,
            "dedupe_key": "patient_data:bad-tools",
            "allowed_tools": ["visit.search_visits", "medical_knowledge.search", "image.analyze_uploaded_image"],
            "max_tool_steps": 20,
        }

        result = apply_server_tool_policy(task)

        self.assertEqual(result["effective_allowed_tools"], ["visit.search_visits"])
        self.assertEqual(result["effective_max_tool_steps"], 5)

    def test_normalize_planned_tasks_generates_task_id_from_dedupe_key(self):
        tasks = normalize_planned_tasks([_semantic_patient_task()], max_tasks=8)

        self.assertEqual(len(tasks), 1)
        self.assertTrue(tasks[0]["task_id"].startswith("patient_data:patient_data_structured_context:"))
        self.assertTrue(tasks[0]["server_generated_task_id"])
        self.assertEqual(tasks[0]["depends_on"], [])

    def test_normalize_planned_tasks_resolves_dedupe_dependencies(self):
        patient = _semantic_patient_task("patient_data:latest_visit")
        knowledge = _semantic_knowledge_task(
            "medical_knowledge:blood_pressure",
            depends_on_dedupe_keys=["patient_data:latest_visit"],
        )

        tasks = normalize_planned_tasks([knowledge, patient], max_tasks=8)
        by_dedupe = {task["dedupe_key"]: task for task in tasks}

        self.assertEqual(
            by_dedupe["medical_knowledge:blood_pressure"]["depends_on"],
            [by_dedupe["patient_data:latest_visit"]["task_id"]],
        )

    def test_normalize_planned_tasks_rejects_bad_dedupe_key_examples(self):
        bad = _semantic_knowledge_task("medical_knowledge:explain_the_report_and_dizziness")

        with self.assertRaises(TaskBoardValidationError) as caught:
            normalize_planned_tasks([bad], max_tasks=8)

        self.assertEqual(caught.exception.rejected_tasks[0]["reason"], "invalid_dedupe_key")

    def test_normalize_planned_tasks_rejects_legacy_depends_on(self):
        task = _semantic_knowledge_task("medical_knowledge:blood_pressure")
        task["depends_on"] = ["patient_data:1"]

        with self.assertRaises(TaskBoardValidationError) as caught:
            normalize_planned_tasks([task], max_tasks=8)

        self.assertEqual(caught.exception.rejected_tasks[0]["reason"], "legacy_depends_on_not_allowed")

    def test_normalize_proposed_tasks_resolves_existing_and_same_batch_dependencies(self):
        existing = normalize_planned_tasks([_semantic_patient_task("patient_data:latest_visit")], max_tasks=8)
        image = {
            "agent": GRAPH_IMAGE_ANALYSIS,
            "task_type": "image_analysis",
            "dedupe_key": "image_analysis:uploaded_report",
            "goal": "Analyze report.",
            "allowed_tools": ["image.analyze_uploaded_image"],
            "max_tool_steps": 1,
        }
        knowledge = _semantic_knowledge_task(
            "medical_knowledge:blood_pressure",
            depends_on_dedupe_keys=["patient_data:latest_visit", "image_analysis:uploaded_report"],
        )

        accepted, rejected = normalize_proposed_tasks([knowledge, image], existing_tasks=existing, max_tasks=2)
        by_dedupe = {task["dedupe_key"]: task for task in accepted}

        self.assertEqual(rejected, [])
        self.assertEqual(len(by_dedupe["medical_knowledge:blood_pressure"]["depends_on"]), 2)

    def test_normalize_proposed_tasks_rejects_dependency_cut_by_task_budget(self):
        knowledge = _semantic_knowledge_task(
            "medical_knowledge:blood_pressure",
            depends_on_dedupe_keys=["patient_data:latest_visit"],
        )
        patient = _semantic_patient_task("patient_data:latest_visit")

        accepted, rejected = normalize_proposed_tasks([knowledge, patient], existing_tasks=[], max_tasks=1)

        self.assertEqual(accepted, [])
        self.assertEqual(rejected[-1]["reason"], "dependency_not_accepted")

    def test_validate_task_board_rejects_invalid_dependency_instead_of_silent_drop(self):
        patient_task = _valid_patient_task()
        knowledge_task = _valid_knowledge_task(depends_on=["image:wrong_id"])

        with self.assertRaises(TaskBoardValidationError) as caught:
            validate_task_board([patient_task, knowledge_task])

        self.assertEqual(caught.exception.rejected_tasks[0]["reason"], "invalid_dependency")

    def test_validate_task_board_rejects_invalid_task_id_prefix(self):
        task = _valid_patient_task(task_id="medical_knowledge:wrong_prefix")

        with self.assertRaises(TaskBoardValidationError) as caught:
            validate_task_board([task])

        self.assertEqual(caught.exception.rejected_tasks[0]["reason"], "invalid_task_id_prefix")

    def test_validate_task_board_rejects_self_dependency_and_cycle(self):
        self_dependent = _valid_patient_task(depends_on=["patient_data:1"])
        with self.assertRaises(TaskBoardValidationError) as caught:
            validate_task_board([self_dependent])
        self.assertEqual(caught.exception.rejected_tasks[0]["reason"], "self_dependency")

        first = _valid_patient_task(task_id="patient_data:a", dedupe_key="patient_data:a", depends_on=["medical_knowledge:b"])
        second = _valid_knowledge_task(task_id="medical_knowledge:b", dedupe_key="medical_knowledge:b", depends_on=["patient_data:a"])
        with self.assertRaises(TaskBoardValidationError) as caught:
            validate_task_board([first, second])
        self.assertEqual(caught.exception.rejected_tasks[0]["reason"], "dependency_cycle")

    def test_validate_proposed_tasks_rejects_bad_dependency_but_keeps_valid_tasks(self):
        existing = [_valid_patient_task(status="done")]
        bad = _valid_knowledge_task(
            task_id="medical_knowledge:bad_dep",
            dedupe_key="medical_knowledge:bad_dep",
            depends_on=["image_analysis:missing"],
        )
        good = _valid_knowledge_task(
            task_id="medical_knowledge:good_dep",
            dedupe_key="medical_knowledge:good_dep",
            depends_on=["patient_data:1"],
        )

        accepted, rejected = validate_proposed_tasks([bad, good], existing_tasks=existing, max_tasks=2)

        self.assertEqual([task["task_id"] for task in accepted], ["medical_knowledge:good_dep"])
        self.assertEqual(rejected[0]["reason"], "invalid_dependency")

    def test_validate_proposed_tasks_allows_dependency_on_later_same_batch_task(self):
        knowledge = _valid_knowledge_task(
            task_id="medical_knowledge:after_patient",
            dedupe_key="medical_knowledge:after_patient",
            depends_on=["patient_data:new"],
        )
        patient = _valid_patient_task(task_id="patient_data:new", dedupe_key="patient_data:new")

        accepted, rejected = validate_proposed_tasks([knowledge, patient], existing_tasks=[], max_tasks=2)

        self.assertEqual(rejected, [])
        self.assertEqual([task["task_id"] for task in accepted], ["medical_knowledge:after_patient", "patient_data:new"])
        self.assertEqual(accepted[0]["depends_on"], ["patient_data:new"])

    def test_validate_proposed_tasks_rejects_dependency_cut_by_task_budget(self):
        knowledge = _valid_knowledge_task(
            task_id="medical_knowledge:after_patient",
            dedupe_key="medical_knowledge:after_patient",
            depends_on=["patient_data:new"],
        )
        image = apply_server_tool_policy(
            {
                "task_id": "image_analysis:new",
                "agent": GRAPH_IMAGE_ANALYSIS,
                "goal": "Analyze image.",
                "status": "pending",
                "depends_on": [],
                "result_key": "image_analysis_result",
                "priority": 85,
                "required": False,
                "dedupe_key": "image_analysis:new",
                "allowed_tools": ["image.analyze_uploaded_image"],
                "max_tool_steps": 1,
            }
        )
        patient = _valid_patient_task(task_id="patient_data:new", dedupe_key="patient_data:new")

        accepted, rejected = validate_proposed_tasks([knowledge, image, patient], existing_tasks=[], max_tasks=2)

        self.assertEqual([task["task_id"] for task in accepted], ["image_analysis:new"])
        self.assertEqual(rejected[-1]["reason"], "dependency_not_accepted")

    def test_planner_falls_back_when_llm_returns_invalid_dependency(self):
        payload = {
            "tasks": [
                dict(
                    _valid_knowledge_task(
                        task_id="medical_knowledge:bad_dep",
                        dedupe_key="medical_knowledge:bad_dep",
                        depends_on=["image_analysis:missing"],
                    )
                )
            ],
            "risk_flags": [],
            "conversation_context_summary": {},
            "planning_notes": "bad dependency",
        }
        state = {
            "message": "What is blood pressure?",
            "agent_trace": [],
            "plan": [],
            "max_tasks": 8,
        }

        result = graph_planner_node(FakeLLMGraphService(payload), state)

        self.assertEqual(result["planner_mode"], "rule_fallback")
        self.assertIn("depends_on is an internal field", result["agent_trace"][-1]["fallback_reason"])

    def test_planner_prefers_structured_output_when_supported(self):
        payload = {
            "tasks": [_semantic_patient_task("patient_data:structured_context")],
            "risk_flags": [],
            "conversation_context_summary": {"active_topics": ["profile"]},
            "planning_notes": "structured",
        }
        state = {
            "message": "Check my patient profile.",
            "agent_trace": [],
            "plan": [],
            "max_tasks": 8,
        }
        service = FakeStructuredGraphService(structured_payload=payload)

        result = graph_planner_node(service, state)

        self.assertEqual(result["planner_mode"], "llm")
        self.assertEqual(result["planner_output_mode"], "structured")
        self.assertEqual(service.llm.structured_invocations, 1)
        self.assertEqual(service.llm.json_invocations, 0)
        self.assertTrue(result["task_board"][0]["task_id"].startswith("patient_data:patient_data_structured_context:"))

    def test_planner_structured_failure_falls_back_to_json_parse(self):
        payload = {
            "tasks": [_semantic_patient_task("patient_data:structured_context")],
            "risk_flags": [],
            "conversation_context_summary": {},
            "planning_notes": "json fallback",
        }
        state = {
            "message": "Check my patient profile.",
            "agent_trace": [],
            "plan": [],
            "max_tasks": 8,
        }
        service = FakeStructuredGraphService(
            structured_payload=None,
            fallback_payload=payload,
            structured_error=ValueError("structured unavailable"),
        )

        result = graph_planner_node(service, state)

        self.assertEqual(result["planner_mode"], "llm")
        self.assertEqual(result["planner_output_mode"], "json_parse_fallback")
        self.assertEqual(service.llm.structured_invocations, 1)
        self.assertEqual(service.llm.json_invocations, 1)
        self.assertIn("structured unavailable", result["agent_trace"][-1]["planner_structured_error"])

    def test_planner_structured_invalid_task_uses_rule_fallback_without_json_retry(self):
        payload = {
            "tasks": [_semantic_knowledge_task("medical_knowledge:explain_the_report_and_dizziness")],
            "risk_flags": [],
            "conversation_context_summary": {},
            "planning_notes": "bad dedupe",
        }
        state = {
            "message": "What is blood pressure?",
            "agent_trace": [],
            "plan": [],
            "max_tasks": 8,
        }
        service = FakeStructuredGraphService(
            structured_payload=payload,
            fallback_payload={
                "tasks": [_semantic_patient_task("patient_data:structured_context")],
                "risk_flags": [],
                "conversation_context_summary": {},
                "planning_notes": "should not be used",
            },
        )

        result = graph_planner_node(service, state)

        self.assertEqual(result["planner_mode"], "rule_fallback")
        self.assertEqual(result["planner_output_mode"], "rule_fallback")
        self.assertEqual(service.llm.structured_invocations, 1)
        self.assertEqual(service.llm.json_invocations, 0)
        self.assertIn("dedupe_key segment looks like a natural-language summary", result["agent_trace"][-1]["fallback_reason"])

    def test_gap_checker_force_finishes_when_round_budget_is_exhausted(self):
        state = {
            "message": "I have chest pain and shortness of breath.",
            "agent_trace": [],
            "task_board": [],
            "worker_events": [],
            "risk_flags": ["chest pain", "shortness of breath"],
            "dispatch_round": 2,
            "max_dispatch_rounds": 2,
            "max_tasks": 8,
            "plan": [],
        }

        result = graph_gap_checker_node(FakeGraphService(), state)

        self.assertFalse(result["need_more_tasks"])
        self.assertEqual(result["finish_reason"], "max_rounds_reached")
        self.assertEqual(result["safety_level"], "urgent")

    def test_gap_checker_force_finishes_continue_without_ready_or_proposed_tasks(self):
        state = {
            "message": "Check my patient data.",
            "agent_trace": [],
            "task_board": [],
            "worker_events": [],
            "dispatch_round": 0,
            "max_dispatch_rounds": 2,
            "max_tasks": 8,
            "plan": [],
        }

        result = graph_gap_checker_node(FakeLLMGraphService(_continue_payload()), state)

        self.assertFalse(result["need_more_tasks"])
        self.assertEqual(result["finish_reason"], "degraded_answer_allowed")
        self.assertEqual(result["accepted_proposed_tasks"], 0)
        self.assertEqual(result["agent_trace"][-1]["force_finish_reason"], "continue_without_ready_or_accepted_tasks")

    def test_gap_checker_force_finishes_when_proposed_tasks_are_deduped(self):
        existing = _valid_patient_task(status="done")
        proposed = dict(existing)
        proposed["task_id"] = "patient_data:duplicate"
        proposed["status"] = "pending"
        proposed["created_by"] = "graph_gap_checker"
        state = {
            "message": "Check my patient data.",
            "agent_trace": [],
            "task_board": [existing],
            "worker_events": [],
            "dispatch_round": 0,
            "max_dispatch_rounds": 2,
            "max_tasks": 8,
            "plan": [],
        }

        result = graph_gap_checker_node(FakeLLMGraphService(_continue_payload([proposed])), state)

        self.assertFalse(result["need_more_tasks"])
        self.assertEqual(result["finish_reason"], "degraded_answer_allowed")
        self.assertEqual(result["accepted_proposed_tasks"], 0)
        self.assertEqual(len(result["task_board"]), 1)

    def test_gap_checker_rejects_invalid_proposed_dependency_without_global_fallback(self):
        proposed = _valid_knowledge_task(
            task_id="medical_knowledge:bad_dep",
            dedupe_key="medical_knowledge:bad_dep",
            depends_on=["image_analysis:missing"],
        )
        state = {
            "message": "Check blood pressure.",
            "agent_trace": [],
            "task_board": [],
            "worker_events": [],
            "dispatch_round": 0,
            "max_dispatch_rounds": 2,
            "max_tasks": 8,
            "plan": [],
        }

        result = graph_gap_checker_node(FakeLLMGraphService(_continue_payload([proposed])), state)

        self.assertEqual(result["replanner_mode"], "llm")
        self.assertEqual(result["rejected_proposed_tasks"], 1)
        self.assertEqual(result["rejected_task_reasons"][0]["reason"], "legacy_depends_on_not_allowed")
        self.assertFalse(result["need_more_tasks"])

    def test_replanner_prefers_structured_output_when_supported(self):
        state = {
            "message": "Check my patient data.",
            "agent_trace": [],
            "task_board": [],
            "worker_events": [],
            "dispatch_round": 0,
            "max_dispatch_rounds": 2,
            "max_tasks": 8,
            "max_new_tasks_per_round": 2,
            "plan": [],
        }
        payload = _continue_payload([_semantic_patient_task("patient_data:structured_context")])
        service = FakeStructuredGraphService(structured_payload=payload)

        result = graph_gap_checker_node(service, state)

        self.assertEqual(result["replanner_mode"], "llm")
        self.assertEqual(result["replanner_output_mode"], "structured")
        self.assertEqual(result["accepted_proposed_tasks"], 1)
        self.assertEqual(service.llm.structured_invocations, 1)
        self.assertEqual(service.llm.json_invocations, 0)

    def test_replanner_structured_failure_falls_back_to_json_parse(self):
        state = {
            "message": "Check my patient data.",
            "agent_trace": [],
            "task_board": [],
            "worker_events": [],
            "dispatch_round": 0,
            "max_dispatch_rounds": 2,
            "max_tasks": 8,
            "max_new_tasks_per_round": 2,
            "plan": [],
        }
        payload = _continue_payload([_semantic_patient_task("patient_data:structured_context")])
        service = FakeStructuredGraphService(
            structured_payload=None,
            fallback_payload=payload,
            structured_error=ValueError("structured unavailable"),
        )

        result = graph_gap_checker_node(service, state)

        self.assertEqual(result["replanner_mode"], "llm")
        self.assertEqual(result["replanner_output_mode"], "json_parse_fallback")
        self.assertEqual(result["accepted_proposed_tasks"], 1)
        self.assertEqual(service.llm.structured_invocations, 1)
        self.assertEqual(service.llm.json_invocations, 1)
        self.assertIn("structured unavailable", result["agent_trace"][-1]["replanner_structured_error"])

    def test_replanner_structured_invalid_proposed_task_is_rejected(self):
        state = {
            "message": "Check blood pressure.",
            "agent_trace": [],
            "task_board": [],
            "worker_events": [],
            "dispatch_round": 0,
            "max_dispatch_rounds": 2,
            "max_tasks": 8,
            "max_new_tasks_per_round": 2,
            "plan": [],
        }
        payload = _continue_payload([_semantic_knowledge_task("medical_knowledge:explain_the_report_and_dizziness")])
        service = FakeStructuredGraphService(structured_payload=payload)

        result = graph_gap_checker_node(service, state)

        self.assertEqual(result["replanner_mode"], "llm")
        self.assertEqual(result["replanner_output_mode"], "structured")
        self.assertEqual(result["rejected_proposed_tasks"], 1)
        self.assertEqual(result["rejected_task_reasons"][0]["reason"], "invalid_dedupe_key")
        self.assertFalse(result["need_more_tasks"])
        self.assertEqual(service.llm.json_invocations, 0)

    def test_gap_checker_allows_continue_when_ready_task_exists(self):
        state = {
            "message": "Check my patient data.",
            "agent_trace": [],
            "task_board": [_valid_patient_task()],
            "worker_events": [],
            "dispatch_round": 0,
            "max_dispatch_rounds": 2,
            "max_tasks": 8,
            "plan": [],
        }

        result = graph_gap_checker_node(FakeLLMGraphService(_continue_payload()), state)

        self.assertTrue(result["need_more_tasks"])
        self.assertEqual(result["finish_reason"], "degraded_answer_allowed")

    def test_gap_checker_allows_continue_when_required_task_can_retry(self):
        failed_task = _valid_patient_task(status="failed")
        state = {
            "message": "Check my patient data.",
            "agent_trace": [],
            "task_board": [failed_task],
            "join_summary": {"required_failed": True},
            "worker_events": [],
            "dispatch_round": 0,
            "max_dispatch_rounds": 2,
            "max_tasks": 8,
            "plan": [],
        }

        result = graph_gap_checker_node(FakeLLMGraphService(_continue_payload()), state)

        self.assertTrue(result["need_more_tasks"])
        self.assertEqual(result["task_board"][0]["status"], "pending")
        self.assertEqual(result["task_board"][0]["retry_count"], 1)

    @unittest.skipIf(StructuredTool is None or AIMessage is None, "langchain-core is not installed")
    def test_bound_react_loop_enforces_total_tool_call_limit(self):
        calls = []

        def fake_tool(value=None):
            calls.append(value)
            return {"ok": True, "value": value}

        tool = StructuredTool.from_function(
            func=fake_tool,
            name="patient.get_patient_profile",
            description="fake patient tool",
        )

        class FakeBoundLLM(object):
            def invoke(self, messages):
                return AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "patient.get_patient_profile", "args": {"value": "one"}, "id": "call-1"},
                        {"name": "patient.get_patient_profile", "args": {"value": "two"}, "id": "call-2"},
                        {"name": "patient.get_patient_profile", "args": {"value": "three"}, "id": "call-3"},
                    ],
                )

        class FakeToolCallingLLM(object):
            def bind_tools(self, tools):
                return FakeBoundLLM()

        class FakeReactService(object):
            llm = FakeToolCallingLLM()

        with self.assertRaises(ValueError):
            run_bounded_react(
                FakeReactService(),
                {"message": "test"},
                {"goal": "test", "effective_max_tool_steps": 2},
                [tool],
                "system",
            )

        self.assertEqual(calls, ["one", "two"])

    @unittest.skipIf(StructuredTool is None, "langchain-core is not installed")
    def test_tool_budget_wrapper_rejects_repeated_deep_retrieve_after_total_limit(self):
        calls = []

        def deep_retrieve(query):
            calls.append(query)
            return {"hits": []}

        tool = StructuredTool.from_function(
            func=deep_retrieve,
            name="medical_knowledge.deep_retrieve",
            description="fake deep retrieval",
        )
        budget = ToolCallBudget(1)
        wrapped = wrap_tools_with_budget([tool], budget)[0]

        wrapped.invoke({"query": "blood pressure"})
        with self.assertRaises(ValueError):
            wrapped.invoke({"query": "blood pressure again"})

        self.assertEqual(calls, ["blood pressure"])

    @unittest.skipIf(StructuredTool is None, "langchain-core is not installed")
    def test_create_react_agent_branch_receives_budget_wrapped_tools(self):
        calls = []

        def fake_tool(value=None):
            calls.append(value)
            return {"ok": True}

        tool = StructuredTool.from_function(
            func=fake_tool,
            name="patient.get_patient_profile",
            description="fake patient tool",
        )

        class FakePrebuiltGraph(object):
            def __init__(self, tools):
                self.tools = tools

            def invoke(self, state, config):
                selected = self.tools[0]
                selected.invoke({"value": "one"})
                selected.invoke({"value": "two"})
                return {"messages": []}

        def fake_create_react_agent(llm, tools, state_modifier=None):
            return FakePrebuiltGraph(tools)

        class FakeInvokeLLM(object):
            def invoke(self, messages):
                return None

        class FakeReactService(object):
            llm = FakeInvokeLLM()

        original_create_react_agent = react_module.create_react_agent
        react_module.create_react_agent = fake_create_react_agent
        try:
            with self.assertRaises(ValueError):
                run_bounded_react(
                    FakeReactService(),
                    {"message": "test"},
                    {"goal": "test", "effective_max_tool_steps": 1},
                    [tool],
                    "system",
                )
        finally:
            react_module.create_react_agent = original_create_react_agent

        self.assertEqual(calls, ["one"])


if __name__ == "__main__":
    unittest.main()
