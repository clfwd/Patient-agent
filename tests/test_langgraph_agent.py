import unittest

from app.agent.graph.router import build_risk_flags, build_task_board, find_ready_tasks, start_next_ready_task
from app.agent.graph.state import GRAPH_IMAGE_ANALYSIS, GRAPH_MEDICAL_KNOWLEDGE_AGENT, GRAPH_MEMORY, GRAPH_PATIENT_DATA


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
