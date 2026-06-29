"""Service for local medical knowledge keyword retrieval."""

from .repositories import MedicalKnowledgeRepository
from .retrieval import rank_chunks


class MedicalKnowledgeService(object):
    def __init__(self, session_factory, retrieval_enabled=True, candidate_limit=200):
        self.session_factory = session_factory
        self.retrieval_enabled = retrieval_enabled
        self.candidate_limit = candidate_limit
        self.retrieval_mode = "keyword" if retrieval_enabled else "disabled"

    def search(self, query, limit=3):
        if not self.retrieval_enabled:
            return []
        with self.session_factory() as session:
            repo = MedicalKnowledgeRepository(session)
            candidates = repo.list_chunks(limit=self.candidate_limit)
            ranked = rank_chunks(query, candidates, limit=limit)
            return [repo.to_search_result(chunk) for chunk in ranked]
