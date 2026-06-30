import json
import unittest

from langgraph.types import Send

import app.agent.graph.react as react_module
from app.agent.graph.capabilities import apply_server_tool_policy
from app.agent.graph.nodes import graph_composer_node, graph_gap_checker_node
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


def _valid_patient_task(task_id="patient_data:1", status="pending", dedupe_key="patient_data:structured_context"):
    return apply_server_tool_policy(
        {
            "task_id": task_id,
            "agent": GRAPH_PATIENT_DATA,
            "goal": "Retrieve patient data.",
            "status": status,
            "depends_on": [],
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


def _continue_payload(proposed_tasks=None):
    return {
        "decision": "continue",
        "finish_reason": "degraded_answer_allowed",
        "missing_evidence": ["patient data"],
        "proposed_tasks": proposed_tasks or [],
        "stop_reason": "need more evidence",
        "confidence": 0.5,
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
