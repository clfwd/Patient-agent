"""Business service for long-term memory extraction, retrieval, and persistence."""

import json
import re
from datetime import datetime, timedelta

from app.db import MessageRepository

from .embedding import MemoryEmbeddingError
from .extractor import LongTermMemoryExtractor, MemoryExtractionError
from .repositories import EventMemoryRepository, MemoryExtractionJobRepository, ProfileMemoryRepository
from .retrieval import LongTermMemoryRetriever


class LongTermMemoryService(object):
    """Coordinates extraction jobs plus event/profile recall."""

    PROFILE_ALLOWED_KEYS = {
        "preferred_summary_length",
        "communication_style",
        "explanation_preference",
        "caregiver_role",
        "response_language_preference",
    }
    PROFILE_BLOCKED_KEYS = {
        "patient_name",
        "gender",
        "date_of_birth",
        "birth_date",
        "age_years",
        "patient_no",
        "phone",
        "id_card",
    }
    PROFILE_KEY_ALIASES = {
        "response_length_preference": "preferred_summary_length",
        "summary_length_preference": "preferred_summary_length",
        "preferred_response_length": "preferred_summary_length",
        "preferred_summary_style": "preferred_summary_length",
        "response_style": "communication_style",
        "preferred_response_style": "communication_style",
        "language_preference": "response_language_preference",
        "preferred_language": "response_language_preference",
    }
    PROFILE_VALUE_ALIASES = {
        "preferred_summary_length": {
            "brief": "concise",
            "short": "concise",
            "concise": "concise",
            "summary_first": "concise",
            "brief_first": "concise",
            "简短": "concise",
            "简洁": "concise",
            "一句话": "concise",
        }
    }

    EVENT_ALLOWED_CATEGORIES = {
        "symptom_progression",
        "medication_adherence",
        "followup_commitment",
        "care_context",
        "temporary_risk_signal",
    }
    EVENT_BLOCKED_CATEGORIES = {
        "medical_record",
        "medical_visit",
        "patient_profile",
        "demographics",
    }
    MIRRORED_EVENT_FIELDS = {
        "record_id",
        "visit_id",
        "visit_no",
        "department",
        "doctor_name",
        "diagnosis",
        "diagnosis_summary",
        "treatment_plan",
        "patient_name",
        "gender",
        "birth_date",
        "date_of_birth",
        "age_years",
    }
    CONCISE_PATTERNS = (
        r"尽量简短",
        r"尽量简洁",
        r"先说结论",
        r"一句话",
        r"简短一点",
        r"简洁一点",
        r"brief",
        r"concise",
    )

    def __init__(
        self,
        main_session_factory,
        memory_session_factory,
        extractor=None,
        embedder=None,
        max_retries=3,
        retrieval_enabled=True,
        dense_topn=10,
        keyword_topn=10,
        retrieval_topk=8,
        rrf_k=60,
    ):
        self.main_session_factory = main_session_factory
        self.memory_session_factory = memory_session_factory
        self.extractor = extractor or LongTermMemoryExtractor()
        self.embedder = embedder
        self.max_retries = max_retries
        self.retrieval_enabled = bool(retrieval_enabled)
        self.retriever = LongTermMemoryRetriever(
            memory_session_factory,
            embedder=embedder,
            dense_topn=dense_topn,
            keyword_topn=keyword_topn,
            topk=retrieval_topk,
            rrf_k=rrf_k,
        )

    @property
    def enabled(self):
        return self.memory_session_factory is not None

    def maybe_create_extraction_job(self, session_id, patient_id):
        if not self.enabled or not session_id or not patient_id:
            return None

        with self.main_session_factory() as main_session:
            repo = MessageRepository(main_session)
            user_sequence_numbers = repo.list_sequence_numbers_by_type(session_id, "user_input")
            if not user_sequence_numbers or len(user_sequence_numbers) % 5 != 0:
                return None
            from_sequence_no = user_sequence_numbers[-5]
            to_sequence_no = repo.get_latest_sequence_no(session_id)

        with self.memory_session_factory() as memory_session:
            job_repo = MemoryExtractionJobRepository(memory_session)
            return job_repo.create_job(
                patient_id=patient_id,
                session_id=session_id,
                from_sequence_no=from_sequence_no,
                to_sequence_no=to_sequence_no,
                status="pending",
                retry_count=0,
                max_retries=self.max_retries,
            )

    def fetch_window_messages(self, session_id, from_sequence_no, to_sequence_no):
        with self.main_session_factory() as main_session:
            repo = MessageRepository(main_session)
            return [repo.to_read_model(item) for item in repo.list_by_session_range(session_id, from_sequence_no, to_sequence_no)]

    @staticmethod
    def _parse_occurred_at(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    @classmethod
    def _normalize_profile(cls, profile):
        normalized = dict(profile or {})
        raw_key = str(normalized.get("key") or "").strip()
        normalized_key = cls.PROFILE_KEY_ALIASES.get(raw_key, raw_key)
        normalized["key"] = normalized_key

        raw_value = str(normalized.get("value") or "").strip()
        if normalized_key in cls.PROFILE_VALUE_ALIASES:
            normalized["value"] = cls.PROFILE_VALUE_ALIASES[normalized_key].get(raw_value, raw_value)
        return normalized

    @classmethod
    def _is_allowed_profile(cls, profile):
        key = str(profile.get("key") or "").strip()
        if not key:
            return False
        if key in cls.PROFILE_BLOCKED_KEYS:
            return False
        if key not in cls.PROFILE_ALLOWED_KEYS:
            return False
        return True

    @classmethod
    def _infer_profiles_from_messages(cls, messages):
        inferred = []
        user_text = "\n".join(
            str(item.get("content") or "")
            for item in messages
            if item.get("role") == "user" and item.get("content")
        )
        if not user_text:
            return inferred

        if any(re.search(pattern, user_text, re.IGNORECASE) for pattern in cls.CONCISE_PATTERNS):
            inferred.append(
                {
                    "key": "preferred_summary_length",
                    "value": "concise",
                    "summary": "User prefers concise, conclusion-first answers unless more detail is requested.",
                    "confidence_score": 0.90,
                }
            )
        return inferred

    @classmethod
    def _is_allowed_event(cls, event):
        category = str(event.get("category") or "").strip()
        if not category:
            return False
        if category in cls.EVENT_BLOCKED_CATEGORIES:
            return False
        if category not in cls.EVENT_ALLOWED_CATEGORIES:
            return False

        payload = event.get("payload") or {}
        if isinstance(payload, dict):
            mirrored_fields = cls.MIRRORED_EVENT_FIELDS.intersection(set(payload.keys()))
            if len(mirrored_fields) >= 2:
                return False

        summary = str(event.get("summary") or "").lower()
        blocked_fragments = (
            "medical record",
            "outpatient clinical note",
            "outpatient visit",
        )
        return not any(fragment in summary for fragment in blocked_fragments)

    @staticmethod
    def _build_embedding_text(event):
        payload = event.get("payload") or {}
        payload_text = ""
        if payload:
            payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        parts = [
            "category: {0}".format(event.get("category") or ""),
            "summary: {0}".format(event.get("summary") or ""),
        ]
        if payload_text:
            parts.append("payload: {0}".format(payload_text))
        return "\n".join(parts)

    @staticmethod
    def _build_search_text(event):
        payload = event.get("payload") or {}
        payload_values = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                if value in (None, ""):
                    continue
                if isinstance(value, (dict, list)):
                    payload_values.append("{0}:{1}".format(key, json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)))
                else:
                    payload_values.append("{0}:{1}".format(key, value))
        parts = [
            str(event.get("category") or "").strip(),
            str(event.get("summary") or "").strip(),
            " ".join(payload_values).strip(),
        ]
        return "\n".join(part for part in parts if part)

    def _persist_events(self, patient_id, session_id, messages, extracted_events):
        if not extracted_events:
            return []

        message_ids = [item["id"] for item in messages if item.get("role") in ("user", "assistant")]
        prepared_events = []
        generated_at = datetime.utcnow()

        for event in extracted_events:
            confidence_score = float(event.get("confidence_score") or 0)
            if confidence_score < 0.75:
                continue
            if not self._is_allowed_event(event):
                continue

            occurred_at = self._parse_occurred_at(event.get("occurred_at"))
            search_text = self._build_search_text(event)
            embedding_text = None
            embedding_vector = None
            embedding_model = None
            embedding_dimensions = None
            embedding_generated_at = None

            if self.embedder is not None and self.embedder.is_configured():
                embedding_text = self._build_embedding_text(event)
                try:
                    embedding_vector = self.embedder.embed_text(embedding_text)
                except MemoryEmbeddingError as exc:
                    raise MemoryExtractionError(str(exc), retryable=exc.retryable)
                embedding_model = self.embedder.model
                embedding_dimensions = len(embedding_vector)
                embedding_generated_at = generated_at

            prepared_events.append(
                {
                    "patient_id": patient_id,
                    "category": event.get("category") or "temporary_risk_signal",
                    "summary": event.get("summary") or "",
                    "payload": event.get("payload") or {},
                    "confidence_score": confidence_score,
                    "search_text": search_text,
                    "embedding_text": embedding_text,
                    "embedding_model": embedding_model,
                    "embedding_dimensions": embedding_dimensions,
                    "embedding_vector": embedding_vector,
                    "embedding_generated_at": embedding_generated_at,
                    "source_session_id": session_id,
                    "source_message_ids": event.get("source_message_ids") or message_ids,
                    "occurred_at": occurred_at,
                    "last_seen_at": generated_at,
                    "expires_at": self.extractor.compute_expiration(event.get("category"), occurred_at),
                }
            )

        persisted = []
        with self.memory_session_factory() as memory_session:
            repo = EventMemoryRepository(memory_session)
            for event_data in prepared_events:
                persisted.append(repo.create_memory(**event_data))
        return persisted

    def _persist_profiles(self, patient_id, session_id, extracted_profiles):
        normalized_profiles = [self._normalize_profile(item) for item in (extracted_profiles or [])]
        if not normalized_profiles:
            return []

        by_key = {}
        for profile in normalized_profiles:
            key = str(profile.get("key") or "").strip()
            if not key:
                continue
            existing = by_key.get(key)
            if existing is None or float(profile.get("confidence_score") or 0) >= float(existing.get("confidence_score") or 0):
                by_key[key] = profile

        persisted = []
        with self.memory_session_factory() as memory_session:
            repo = ProfileMemoryRepository(memory_session)
            for profile in by_key.values():
                confidence_score = float(profile.get("confidence_score") or 0)
                if confidence_score < 0.80:
                    continue
                if not self._is_allowed_profile(profile):
                    continue
                persisted.append(
                    repo.upsert_memory(
                        patient_id=patient_id,
                        key=profile.get("key") or "unknown_profile",
                        value=profile.get("value") or "unknown",
                        summary=profile.get("summary") or "",
                        confidence_score=confidence_score,
                        source_session_id=session_id,
                        last_seen_at=datetime.utcnow(),
                    )
                )
        return persisted

    @staticmethod
    def _retry_delay(job):
        schedule = [30, 120, 600]
        current_retry = int(job.retry_count or 0)
        if current_retry >= len(schedule):
            return None
        return timedelta(seconds=schedule[current_retry])

    def process_job(self, job_id):
        if not self.enabled:
            return None

        with self.memory_session_factory() as memory_session:
            job_repo = MemoryExtractionJobRepository(memory_session)
            job = job_repo.get_by_id(job_id)
            if job is None:
                return None

        messages = self.fetch_window_messages(job.session_id, job.from_sequence_no, job.to_sequence_no)
        try:
            extracted = self.extractor.extract(job.patient_id, job.session_id, messages)
            self._persist_events(job.patient_id, job.session_id, messages, extracted.get("events") or [])
            profiles = list(extracted.get("profiles") or [])
            profiles.extend(self._infer_profiles_from_messages(messages))
            self._persist_profiles(job.patient_id, job.session_id, profiles)
        except MemoryExtractionError as exc:
            retry_delay = self._retry_delay(job) if exc.retryable else None
            with self.memory_session_factory() as memory_session:
                MemoryExtractionJobRepository(memory_session).mark_retry_or_failed(
                    job.id,
                    str(exc),
                    retry_delay_seconds=retry_delay,
                )
            return None
        except Exception as exc:
            retry_delay = self._retry_delay(job)
            with self.memory_session_factory() as memory_session:
                MemoryExtractionJobRepository(memory_session).mark_retry_or_failed(
                    job.id,
                    str(exc),
                    retry_delay_seconds=retry_delay,
                )
            return None

        with self.memory_session_factory() as memory_session:
            return MemoryExtractionJobRepository(memory_session).mark_completed(job.id)

    def claim_and_process_next_job(self):
        if not self.enabled:
            return None
        with self.memory_session_factory() as memory_session:
            job = MemoryExtractionJobRepository(memory_session).claim_next_job()
        if job is None:
            return None
        return self.process_job(job.id)

    def list_event_memories(self, patient_id, limit=50):
        with self.memory_session_factory() as memory_session:
            repo = EventMemoryRepository(memory_session)
            return [repo.to_read_model(item) for item in repo.list_by_patient(patient_id, limit=limit)]

    def list_profile_memories(self, patient_id, limit=50):
        with self.memory_session_factory() as memory_session:
            repo = ProfileMemoryRepository(memory_session)
            return [repo.to_read_model(item) for item in repo.list_by_patient(patient_id, limit=limit)]

    def recall_long_term_memories(self, patient_id, query, profile_limit=5):
        if not self.enabled or not self.retrieval_enabled or not patient_id or not query:
            return {
                "profiles": [],
                "dense_hits": [],
                "keyword_hits": [],
                "fused_hits": [],
            }
        return self.retriever.recall_long_term_memories(patient_id, query, profile_limit=profile_limit)

    def get_job(self, job_id):
        with self.memory_session_factory() as memory_session:
            job_repo = MemoryExtractionJobRepository(memory_session)
            job = job_repo.get_by_id(job_id)
            if job is None:
                return None
            return job_repo.to_read_model(job)
