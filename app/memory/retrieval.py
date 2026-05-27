"""Hybrid retrieval helpers for long-term memory recall."""

import math
import os
import re
from collections import defaultdict

from sqlalchemy import text

from .repositories import EventMemoryRepository, ProfileMemoryRepository


def _vector_to_pg_text(values):
    return "[{0}]".format(",".join("{0:.12g}".format(float(item)) for item in values))


def _tokenize_query(text_value):
    return [token for token in re.split(r"\W+", str(text_value or "").lower()) if token]


def _embedding_dimensions(embedder, default=1024):
    if embedder is not None and getattr(embedder, "dimensions", None):
        try:
            return max(int(embedder.dimensions), 1)
        except (TypeError, ValueError):
            pass
    raw = str(os.getenv("MEMORY_EMBEDDING_DIMENSIONS", default)).strip()
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        digits = "".join(ch for ch in raw if ch.isdigit())
        return max(int(digits or default), 1)


def _cosine_similarity(left, right):
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = math.sqrt(sum(float(a) * float(a) for a in left))
    right_norm = math.sqrt(sum(float(b) * float(b) for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class LongTermMemoryRetriever(object):
    """Runs profile recall plus dense and keyword retrieval over event memories."""

    def __init__(self, memory_session_factory, embedder=None, dense_topn=10, keyword_topn=10, topk=8, rrf_k=60):
        self.memory_session_factory = memory_session_factory
        self.embedder = embedder
        self.dense_topn = dense_topn
        self.keyword_topn = keyword_topn
        self.topk = topk
        self.rrf_k = rrf_k

    def recall_profile_memories(self, patient_id, limit=5):
        if self.memory_session_factory is None or not patient_id:
            return []
        with self.memory_session_factory() as memory_session:
            repo = ProfileMemoryRepository(memory_session)
            return [repo.to_read_model(item) for item in repo.list_by_patient(patient_id, limit=limit)]

    def dense_search_events(self, patient_id, query, topn=None):
        topn = topn or self.dense_topn
        if not patient_id or not query or self.memory_session_factory is None:
            return []
        if self.embedder is None or not self.embedder.is_configured():
            return []
        query_vector = self.embedder.embed_text(query)
        with self.memory_session_factory() as memory_session:
            engine_name = memory_session.bind.dialect.name if memory_session.bind is not None else ""
            if engine_name == "postgresql":
                return self._dense_search_postgresql(memory_session, patient_id, query_vector, topn=topn)
            return self._dense_search_fallback(memory_session, patient_id, query_vector, topn=topn)

    def _dense_search_postgresql(self, memory_session, patient_id, query_vector, topn):
        repo = EventMemoryRepository(memory_session)
        embedding_dimensions = _embedding_dimensions(self.embedder)
        sql = text(
            """
            SELECT id, 1 - ((embedding_vector::vector({embedding_dimensions})) <=> CAST(:query_vector AS vector({embedding_dimensions}))) AS score
            FROM event_memory
            WHERE patient_id = :patient_id
              AND embedding_vector IS NOT NULL
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY (embedding_vector::vector({embedding_dimensions})) <=> CAST(:query_vector AS vector({embedding_dimensions})), created_at DESC
            LIMIT :topn
            """
            .format(embedding_dimensions=embedding_dimensions)
        )
        rows = memory_session.execute(
            sql,
            {
                "patient_id": patient_id,
                "query_vector": _vector_to_pg_text(query_vector),
                "topn": int(topn),
            },
        ).mappings().all()
        if not rows:
            return []
        score_map = {row["id"]: float(row["score"] or 0.0) for row in rows}
        memories = {item.id: item for item in repo.get_by_ids(score_map.keys())}
        results = []
        for rank, row in enumerate(rows, start=1):
            memory = memories.get(row["id"])
            if memory is None:
                continue
            results.append(
                {
                    "memory": repo.to_read_model(memory),
                    "score": score_map[row["id"]],
                    "rank": rank,
                    "source": "dense",
                }
            )
        return results

    def _dense_search_fallback(self, memory_session, patient_id, query_vector, topn):
        repo = EventMemoryRepository(memory_session)
        scored = []
        for memory in repo.list_active_by_patient(patient_id, limit=max(topn * 10, 50)):
            similarity = _cosine_similarity(query_vector, memory.embedding_vector)
            if similarity <= 0:
                continue
            scored.append((similarity, memory))
        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [
            {
                "memory": repo.to_read_model(memory),
                "score": float(score),
                "rank": rank,
                "source": "dense",
            }
            for rank, (score, memory) in enumerate(scored[:topn], start=1)
        ]

    def keyword_search_events(self, patient_id, query, topn=None):
        topn = topn or self.keyword_topn
        if not patient_id or not query or self.memory_session_factory is None:
            return []
        with self.memory_session_factory() as memory_session:
            engine_name = memory_session.bind.dialect.name if memory_session.bind is not None else ""
            if engine_name == "postgresql":
                return self._keyword_search_postgresql(memory_session, patient_id, query, topn=topn)
            return self._keyword_search_fallback(memory_session, patient_id, query, topn=topn)

    def _keyword_search_postgresql(self, memory_session, patient_id, query, topn):
        repo = EventMemoryRepository(memory_session)
        sql = text(
            """
            SELECT id, ts_rank_cd(search_tsv, plainto_tsquery('simple', :query)) AS score
            FROM event_memory
            WHERE patient_id = :patient_id
              AND (expires_at IS NULL OR expires_at > NOW())
              AND search_tsv @@ plainto_tsquery('simple', :query)
            ORDER BY score DESC, created_at DESC
            LIMIT :topn
            """
        )
        rows = memory_session.execute(
            sql,
            {
                "patient_id": patient_id,
                "query": query,
                "topn": int(topn),
            },
        ).mappings().all()
        if not rows:
            return []
        score_map = {row["id"]: float(row["score"] or 0.0) for row in rows}
        memories = {item.id: item for item in repo.get_by_ids(score_map.keys())}
        results = []
        for rank, row in enumerate(rows, start=1):
            memory = memories.get(row["id"])
            if memory is None:
                continue
            results.append(
                {
                    "memory": repo.to_read_model(memory),
                    "score": score_map[row["id"]],
                    "rank": rank,
                    "source": "keyword",
                }
            )
        return results

    def _keyword_search_fallback(self, memory_session, patient_id, query, topn):
        repo = EventMemoryRepository(memory_session)
        query_tokens = _tokenize_query(query)
        scored = []
        for memory in repo.list_active_by_patient(patient_id, limit=max(topn * 10, 50)):
            haystack = " ".join(
                filter(
                    None,
                    [
                        str(memory.category or ""),
                        str(memory.summary or ""),
                        str(memory.search_text or ""),
                    ],
                )
            ).lower()
            token_hits = sum(1 for token in query_tokens if token and token in haystack)
            if token_hits <= 0:
                continue
            score = float(token_hits) / float(max(len(query_tokens), 1))
            scored.append((score, memory))
        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [
            {
                "memory": repo.to_read_model(memory),
                "score": float(score),
                "rank": rank,
                "source": "keyword",
            }
            for rank, (score, memory) in enumerate(scored[:topn], start=1)
        ]

    def fuse_with_rrf(self, dense_results, keyword_results, topk=None, rrf_k=None):
        topk = topk or self.topk
        rrf_k = rrf_k or self.rrf_k
        score_map = defaultdict(float)
        hit_map = {}

        for source_name, results in (("dense", dense_results or []), ("keyword", keyword_results or [])):
            for default_rank, item in enumerate(results, start=1):
                memory = item.get("memory") or {}
                memory_id = memory.get("id")
                if not memory_id:
                    continue
                rank = int(item.get("rank") or default_rank)
                score_map[memory_id] += 1.0 / float(rrf_k + rank)
                hit_map.setdefault(memory_id, memory)
                hit_map[memory_id] = memory

        ranked = sorted(score_map.items(), key=lambda item: item[1], reverse=True)
        fused = []
        for output_rank, (memory_id, score) in enumerate(ranked[:topk], start=1):
            fused.append(
                {
                    "memory": hit_map[memory_id],
                    "score": float(score),
                    "rank": output_rank,
                    "source": "rrf",
                }
            )
        return fused

    def recall_long_term_memories(self, patient_id, query, profile_limit=5):
        profiles = self.recall_profile_memories(patient_id, limit=profile_limit)
        dense_hits = self.dense_search_events(patient_id, query, topn=self.dense_topn)
        keyword_hits = self.keyword_search_events(patient_id, query, topn=self.keyword_topn)
        fused_hits = self.fuse_with_rrf(dense_hits, keyword_hits, topk=self.topk, rrf_k=self.rrf_k)
        return {
            "profiles": profiles,
            "dense_hits": dense_hits,
            "keyword_hits": keyword_hits,
            "fused_hits": fused_hits,
        }
