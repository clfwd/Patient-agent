import unittest

from fastapi.testclient import TestClient

from app.main import create_app
from app.memory.repositories import MemoryExtractionJobRepository, ProfileMemoryRepository


class StubMemoryExtractor(object):
    def __init__(self, events=None, profiles=None, error=None):
        self.events = events or []
        self.profiles = profiles or []
        self.error = error

    def extract(self, patient_id, session_id, messages):
        if self.error is not None:
            raise self.error
        return {
            "events": list(self.events),
            "profiles": list(self.profiles),
        }

    @staticmethod
    def compute_expiration(category, occurred_at=None):
        from datetime import datetime, timedelta

        return (occurred_at or datetime.utcnow()) + timedelta(days=30)


class RetryableError(Exception):
    pass


class StubEmbeddingClient(object):
    def __init__(self, vector=None, model="text-embedding-v4"):
        self.vector = vector or [0.12, 0.34, 0.56]
        self.model = model

    def is_configured(self):
        return True

    def embed_text(self, text):
        return list(self.vector)


class MemoryApiTest(unittest.TestCase):
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
                "patient_no": "PMEM001",
                "name": "Wang Li",
                "gender": "female",
                "phone": "13900000088",
                "id_card": "310101199901018888",
            },
        )
        self.assertEqual(patient_response.status_code, 200)
        self.patient = patient_response.json()
        self.app.state.agent_service.llm = None
        self.app.state.agent_service.tool_calling_backend = None

    def tearDown(self):
        self.client.close()

    def _invoke_follow_up(self, session_id=None, message="Please keep tracking my situation."):
        payload = {
            "message": message,
            "patient_id": self.patient["id"],
            "verify_phone": "13900000088",
            "with_audio": False,
        }
        if session_id:
            payload["session_id"] = session_id
        response = self.client.post("/api/v1/agent/invoke", json=payload)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_fifth_turn_creates_job_and_processing_persists_memories(self):
        self.app.state.memory_service.extractor = StubMemoryExtractor(
            events=[
                {
                    "category": "followup_commitment",
                    "summary": "Parent plans to continue following up if symptoms do not improve.",
                    "payload": {"topic": "follow_up"},
                    "confidence_score": 0.81,
                    "source_message_ids": [],
                }
            ],
            profiles=[
                {
                    "key": "preferred_summary_length",
                    "value": "concise",
                    "summary": "User prefers concise summaries.",
                    "confidence_score": 0.84,
                }
            ],
        )
        self.app.state.memory_service.embedder = StubEmbeddingClient()

        session_id = None
        for index in range(5):
            body = self._invoke_follow_up(
                session_id=session_id,
                message="Turn {0}: please keep following up.".format(index + 1),
            )
            session_id = body["session_id"]

        with self.app.state.MemorySessionLocal() as session:
            pending_jobs = MemoryExtractionJobRepository(session).list_pending(limit=10)
            self.assertEqual(len(pending_jobs), 1)
            job_id = pending_jobs[0].id

        self.app.state.memory_service.claim_and_process_next_job()

        job_response = self.client.get("/api/v1/memory/jobs/{0}".format(job_id))
        self.assertEqual(job_response.status_code, 200)
        self.assertEqual(job_response.json()["status"], "completed")

        events_response = self.client.get("/api/v1/memory/patients/{0}/events".format(self.patient["id"]))
        self.assertEqual(events_response.status_code, 200)
        self.assertEqual(len(events_response.json()), 1)
        self.assertEqual(events_response.json()[0]["category"], "followup_commitment")
        self.assertEqual(events_response.json()[0]["has_embedding"], True)
        self.assertEqual(events_response.json()[0]["embedding_model"], "text-embedding-v4")
        self.assertEqual(events_response.json()[0]["embedding_dimensions"], 3)
        self.assertIsNotNone(events_response.json()[0]["embedding_generated_at"])

        profiles_response = self.client.get("/api/v1/memory/patients/{0}/profiles".format(self.patient["id"]))
        self.assertEqual(profiles_response.status_code, 200)
        self.assertEqual(len(profiles_response.json()), 1)
        self.assertEqual(profiles_response.json()[0]["key"], "preferred_summary_length")

    def test_profile_memory_requires_confidence_margin_before_overwrite(self):
        with self.app.state.MemorySessionLocal() as session:
            repo = ProfileMemoryRepository(session)
            repo.upsert_memory(
                patient_id=self.patient["id"],
                key="communication_style",
                value="brief_first",
                summary="Prefers a brief conclusion first.",
                confidence_score=0.86,
                source_session_id="session-a",
            )
            repo.upsert_memory(
                patient_id=self.patient["id"],
                key="communication_style",
                value="detailed_first",
                summary="Prefers detailed explanation first.",
                confidence_score=0.88,
                source_session_id="session-b",
            )
            record = repo.get_by_patient_and_key(self.patient["id"], "communication_style")
            self.assertEqual(record.value, "brief_first")
            repo.upsert_memory(
                patient_id=self.patient["id"],
                key="communication_style",
                value="detailed_first",
                summary="Prefers detailed explanation first.",
                confidence_score=0.93,
                source_session_id="session-c",
            )
            refreshed = repo.get_by_patient_and_key(self.patient["id"], "communication_style")
            self.assertEqual(refreshed.value, "detailed_first")

    def test_retryable_extraction_error_requeues_job(self):
        class RetryableExtractionError(Exception):
            retryable = True

        self.app.state.memory_service.extractor = StubMemoryExtractor(error=RetryableExtractionError("temporary llm error"))

        session_id = None
        for index in range(5):
            body = self._invoke_follow_up(
                session_id=session_id,
                message="Retry test turn {0}.".format(index + 1),
            )
            session_id = body["session_id"]

        with self.app.state.MemorySessionLocal() as session:
            pending_jobs = MemoryExtractionJobRepository(session).list_pending(limit=10)
            self.assertEqual(len(pending_jobs), 1)
            job_id = pending_jobs[0].id

        self.app.state.memory_service.claim_and_process_next_job()

        job = self.app.state.memory_service.get_job(job_id)
        self.assertEqual(job["status"], "pending")
        self.assertEqual(job["retry_count"], 1)
        self.assertIsNotNone(job["next_retry_at"])

    def test_profile_demographics_are_filtered_out(self):
        self.app.state.memory_service.extractor = StubMemoryExtractor(
            profiles=[
                {
                    "key": "patient_name",
                    "value": "Huang Lei",
                    "summary": "Patient legal name",
                    "confidence_score": 0.99,
                },
                {
                    "key": "preferred_summary_length",
                    "value": "concise",
                    "summary": "User prefers concise summaries",
                    "confidence_score": 0.91,
                },
            ]
        )

        session_id = None
        for index in range(5):
            body = self._invoke_follow_up(
                session_id=session_id,
                message="Profile filter test turn {0}.".format(index + 1),
            )
            session_id = body["session_id"]

        self.app.state.memory_service.claim_and_process_next_job()

        profiles_response = self.client.get("/api/v1/memory/patients/{0}/profiles".format(self.patient["id"]))
        self.assertEqual(profiles_response.status_code, 200)
        profiles = profiles_response.json()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["key"], "preferred_summary_length")

    def test_profile_preference_is_inferred_from_user_wording(self):
        self.app.state.memory_service.extractor = StubMemoryExtractor(events=[], profiles=[])

        session_id = None
        messages = [
            "Please keep following up.",
            "The cough is worse at night.",
            "The child is resisting medicine.",
            "If fever returns tonight, we will revisit tomorrow.",
            "以后回答我时尽量简短一点，先说结论就行。",
        ]
        for message in messages:
            body = self._invoke_follow_up(session_id=session_id, message=message)
            session_id = body["session_id"]

        self.app.state.memory_service.claim_and_process_next_job()

        profiles_response = self.client.get("/api/v1/memory/patients/{0}/profiles".format(self.patient["id"]))
        self.assertEqual(profiles_response.status_code, 200)
        profiles = profiles_response.json()
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["key"], "preferred_summary_length")
        self.assertEqual(profiles[0]["value"], "concise")

    def test_medical_record_like_events_are_filtered_out(self):
        self.app.state.memory_service.extractor = StubMemoryExtractor(
            events=[
                {
                    "category": "medical_record",
                    "summary": "Detailed outpatient clinical note confirming viral upper respiratory infection",
                    "payload": {
                        "record_id": "record-1",
                        "doctor_name": "Dr Lin",
                        "diagnosis": "URI",
                        "treatment_plan": "Rest",
                    },
                    "confidence_score": 0.95,
                    "source_message_ids": [],
                },
                {
                    "category": "followup_commitment",
                    "summary": "Parent will seek another follow-up if fever persists tonight.",
                    "payload": {
                        "plan": "return_if_fever_persists",
                    },
                    "confidence_score": 0.86,
                    "source_message_ids": [],
                },
            ]
        )

        session_id = None
        for index in range(5):
            body = self._invoke_follow_up(
                session_id=session_id,
                message="Event filter test turn {0}.".format(index + 1),
            )
            session_id = body["session_id"]

        self.app.state.memory_service.claim_and_process_next_job()

        events_response = self.client.get("/api/v1/memory/patients/{0}/events".format(self.patient["id"]))
        self.assertEqual(events_response.status_code, 200)
        events = events_response.json()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["category"], "followup_commitment")
