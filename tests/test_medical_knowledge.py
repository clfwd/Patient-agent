import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.knowledge.repositories import MedicalKnowledgeRepository
from app.knowledge.service import MedicalKnowledgeService
from app.main import create_app


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "medical_knowledge_seed.json"


class MedicalKnowledgeTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            "sqlite:///:memory:",
            memory_database_url="sqlite:///:memory:",
            start_memory_worker=False,
        )
        self.client = TestClient(self.app)
        self.service = MedicalKnowledgeService(self.app.state.SessionLocal)

    def tearDown(self):
        self.client.close()

    def _seed_fixture(self):
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        with self.app.state.SessionLocal() as session:
            repo = MedicalKnowledgeRepository(session)
            for item in payload:
                document = repo.create_document(
                    title=item["title"],
                    source=item["source"],
                    source_type=item["source_type"],
                    content=item["content"],
                )
                repo.create_chunks(document.id, item["chunks"])

    def test_create_document_chunks_and_keyword_search(self):
        with self.app.state.SessionLocal() as session:
            repo = MedicalKnowledgeRepository(session)
            document = repo.create_document(
                title="Blood Sugar Basics",
                source="unit-test",
                source_type="fixture",
                content="Blood sugar overview.",
            )
            repo.create_chunks(
                document.id,
                [
                    {
                        "content": "Blood sugar is glucose in the blood.",
                        "search_text": "blood sugar glucose 血糖",
                    }
                ],
            )

        results = self.service.search("blood sugar meaning", limit=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Blood Sugar Basics")
        self.assertEqual(results[0]["source"], "unit-test")
        self.assertTrue(results[0]["document_id"])
        self.assertTrue(results[0]["chunk_id"])
        self.assertIn("glucose", results[0]["content"])

    def test_search_returns_empty_list_when_no_keyword_matches(self):
        self._seed_fixture()

        results = self.service.search("orthopedic cast replacement", limit=3)

        self.assertEqual(results, [])

    def test_fixture_seed_can_be_retrieved_without_external_network(self):
        self._seed_fixture()

        results = self.service.search("fever hydration", limit=3)

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Fever Home Care")
        self.assertIn("test-fixture", results[0]["source"])
