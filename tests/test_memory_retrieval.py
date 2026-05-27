import unittest

from fastapi.testclient import TestClient

from app.main import create_app


class StubMemoryExtractor(object):
    def __init__(self, events=None, profiles=None):
        self.events = events or []
        self.profiles = profiles or []

    def extract(self, patient_id, session_id, messages):
        return {
            "events": list(self.events),
            "profiles": list(self.profiles),
        }

    @staticmethod
    def compute_expiration(category, occurred_at=None):
        from datetime import datetime, timedelta

        return (occurred_at or datetime.utcnow()) + timedelta(days=30)


class QueryAwareEmbeddingClient(object):
    def __init__(self, model="text-embedding-v4"):
        self.model = model

    def is_configured(self):
        return True

    def embed_text(self, text):
        normalized = str(text or "").lower()
        if "fever" in normalized or "revisit" in normalized or "复诊" in normalized:
            return [0.0, 1.0]
        if "night" in normalized or "cough" in normalized or "咳" in normalized:
            return [1.0, 0.0]
        return [0.5, 0.5]


class MemoryRetrievalApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            "sqlite:///:memory:",
            memory_database_url="sqlite:///:memory:",
            start_memory_worker=False,
        )
        self.client = TestClient(self.app)
        patient_response = self.client.post(
            "/api/v1/patients",
            json={
                "patient_no": "PMEMR001",
                "name": "Zhang San",
                "gender": "male",
                "phone": "13900000066",
                "id_card": "310101199901016666",
            },
        )
        self.assertEqual(patient_response.status_code, 200)
        self.patient = patient_response.json()
        self.app.state.agent_service.llm = None
        self.app.state.agent_service.tool_calling_backend = None
        self.app.state.memory_service.extractor = StubMemoryExtractor(
            events=[
                {
                    "category": "symptom_progression",
                    "summary": "Child's cough worsens at night and disrupts sleep.",
                    "payload": {
                        "timing_pattern": "nocturnal_worsening",
                        "impact": "sleep_disruption",
                    },
                    "confidence_score": 0.95,
                },
                {
                    "category": "followup_commitment",
                    "summary": "Parent plans in-person revisit tomorrow if fever returns tonight.",
                    "payload": {
                        "trigger_condition": "fever_returns",
                        "intended_action": "revisit_tomorrow",
                    },
                    "confidence_score": 0.91,
                },
            ],
            profiles=[
                {
                    "key": "preferred_summary_length",
                    "value": "concise",
                    "summary": "User prefers concise, conclusion-first answers.",
                    "confidence_score": 0.92,
                }
            ],
        )
        self.app.state.memory_service.embedder = QueryAwareEmbeddingClient()
        self.app.state.memory_service.retriever.embedder = self.app.state.memory_service.embedder

    def tearDown(self):
        self.client.close()

    def _invoke_follow_up(self, message, session_id=None):
        payload = {
            "message": message,
            "patient_id": self.patient["id"],
            "verify_phone": "13900000066",
            "with_audio": False,
        }
        if session_id:
            payload["session_id"] = session_id
        response = self.client.post("/api/v1/agent/invoke", json=payload)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _seed_memories(self):
        session_id = None
        messages = [
            "The cough is worse at night.",
            "The child wakes up because of coughing.",
            "The child resists medicine sometimes.",
            "If fever returns tonight, we will revisit tomorrow.",
            "Please answer briefly with the conclusion first.",
        ]
        for message in messages:
            body = self._invoke_follow_up(message, session_id=session_id)
            session_id = body["session_id"]
        self.app.state.memory_service.claim_and_process_next_job()
        return session_id

    def test_recall_endpoint_returns_dense_keyword_and_fused_hits(self):
        self._seed_memories()

        response = self.client.post(
            "/api/v1/memory/patients/{0}/recall".format(self.patient["id"]),
            json={"query": "night cough"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["profiles"][0]["key"], "preferred_summary_length")
        self.assertGreaterEqual(len(payload["dense_hits"]), 1)
        self.assertGreaterEqual(len(payload["keyword_hits"]), 1)
        self.assertGreaterEqual(len(payload["fused_hits"]), 1)
        self.assertIn("cough", payload["fused_hits"][0]["memory"]["summary"].lower())
        self.assertTrue(payload["fused_hits"][0]["memory"]["has_embedding"])

    def test_recall_endpoint_can_prioritize_followup_event(self):
        self._seed_memories()

        response = self.client.post(
            "/api/v1/memory/patients/{0}/recall".format(self.patient["id"]),
            json={"query": "fever revisit tomorrow"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertGreaterEqual(len(payload["fused_hits"]), 1)
        self.assertIn("revisit", payload["fused_hits"][0]["memory"]["summary"].lower())
