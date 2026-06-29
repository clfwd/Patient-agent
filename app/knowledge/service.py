"""Service for local medical knowledge keyword retrieval."""

from .repositories import MedicalKnowledgeRepository
from .retrieval import rank_chunks, rrf_rank_chunks, tokenize_query


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

    def deep_retrieve(self, query, limit=5):
        if not self.retrieval_enabled:
            return {
                "summary": "",
                "key_points": [],
                "sources": [],
                "coverage": {},
                "limitations": ["medical knowledge retrieval is disabled"],
                "hits": [],
                "retrieval_mode": "disabled",
            }

        queries = self._rewrite_queries(query)
        with self.session_factory() as session:
            repo = MedicalKnowledgeRepository(session)
            candidates = repo.list_chunks(limit=self.candidate_limit)
            ranked = rrf_rank_chunks(queries, candidates, limit=limit)
            hits = [repo.to_search_result(chunk) for chunk in ranked]
        return self._compress_results(query, queries, hits)

    def _rewrite_queries(self, query):
        text = str(query or "").strip()
        tokens = tokenize_query(text)
        queries = [text] if text else []
        if tokens:
            queries.append(" ".join(tokens[:8]))
        lowered = text.lower()
        expansions = []
        if "blood pressure" in lowered or "hypertension" in lowered or "血压" in text:
            expansions.extend(["blood pressure hypertension dizziness", "high blood pressure emergency chest pain shortness of breath"])
        if "blood sugar" in lowered or "glucose" in lowered or "血糖" in text:
            expansions.extend(["blood sugar glucose HbA1c fasting glucose", "diabetes blood glucose test indicator"])
        if "fever" in lowered or "发热" in text:
            expansions.append("fever hydration warning signs")
        if "chest pain" in lowered or "shortness of breath" in lowered or "胸痛" in text or "呼吸困难" in text:
            expansions.append("chest pain shortness of breath emergency care")
        queries.extend(expansions)
        result = []
        seen = set()
        for item in queries:
            normalized = " ".join(str(item or "").split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result or [text]

    def _compress_results(self, query, queries, hits):
        key_points = []
        sources = []
        coverage = {}
        for hit in hits:
            content = hit.get("content") or ""
            if content:
                key_points.append(content[:240])
            sources.append(
                {
                    "title": hit.get("title"),
                    "source": hit.get("source"),
                    "document_id": hit.get("document_id"),
                    "chunk_id": hit.get("chunk_id"),
                }
            )
        tokens = tokenize_query(query)
        joined = " ".join(hit.get("content") or "" for hit in hits).lower()
        for token in tokens:
            coverage[token] = token.lower() in joined
        summary = " ".join(key_points[:2])[:500]
        limitations = []
        if not hits:
            limitations.append("no matching local medical knowledge chunks were found")
        return {
            "summary": summary,
            "key_points": key_points[:5],
            "sources": sources,
            "coverage": coverage,
            "limitations": limitations,
            "hits": hits,
            "queries": queries,
            "retrieval_mode": "deep_keyword_rrf",
        }
