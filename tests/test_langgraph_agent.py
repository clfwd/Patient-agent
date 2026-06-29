import unittest

from langgraph.types import Send

from app.agent.graph.nodes import graph_composer_node
from app.agent.graph.router import (
    build_risk_flags,
    build_task_board,
    find_ready_tasks,
    route_after_dispatcher,
    start_next_ready_task,
    start_ready_tasks,
)
from app.agent.graph.state import GRAPH_IMAGE_ANALYSIS, GRAPH_MEDICAL_KNOWLEDGE_AGENT, GRAPH_MEMORY, GRAPH_PATIENT_DATA


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


if __name__ == "__main__":
    unittest.main()
