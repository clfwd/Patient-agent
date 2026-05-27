"""Repositories for long-term memory persistence and job control."""

import json
from datetime import datetime

from sqlalchemy import asc, desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from .models import EventMemory, MemoryExtractionJob, ProfileMemory


class EventMemoryRepository(object):
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _serialize_payload(payload):
        if payload in (None, ""):
            return None
        return json.dumps(payload, ensure_ascii=False, default=str)

    @staticmethod
    def _deserialize_payload(payload_json):
        if not payload_json:
            return None
        try:
            return json.loads(payload_json)
        except (TypeError, ValueError):
            return {"raw": payload_json}

    def create_memory(self, **memory_data):
        payload = memory_data.pop("payload", None)
        source_message_ids = memory_data.pop("source_message_ids", None)
        memory = EventMemory(
            payload_json=self._serialize_payload(payload),
            source_message_ids_json=self._serialize_payload(source_message_ids),
            **memory_data
        )
        self.session.add(memory)
        self.session.commit()
        self.session.refresh(memory)
        return memory

    def get_by_id(self, memory_id):
        return self.session.get(EventMemory, memory_id)

    def get_by_ids(self, memory_ids):
        if not memory_ids:
            return []
        stmt = select(EventMemory).where(EventMemory.id.in_(list(memory_ids)))
        return self.session.execute(stmt).scalars().all()

    def list_by_patient(self, patient_id, limit=50):
        stmt = (
            select(EventMemory)
            .where(EventMemory.patient_id == patient_id)
            .order_by(desc(EventMemory.created_at))
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()

    def list_active_by_patient(self, patient_id, limit=200):
        now = datetime.utcnow()
        stmt = (
            select(EventMemory)
            .where(
                EventMemory.patient_id == patient_id,
                or_(EventMemory.expires_at.is_(None), EventMemory.expires_at > now),
            )
            .order_by(desc(EventMemory.created_at))
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()

    def to_read_model(self, memory):
        return {
            "id": memory.id,
            "patient_id": memory.patient_id,
            "category": memory.category,
            "summary": memory.summary,
            "payload": self._deserialize_payload(memory.payload_json),
            "confidence_score": memory.confidence_score,
            "search_text": memory.search_text,
            "has_embedding": bool(memory.embedding_vector),
            "embedding_model": memory.embedding_model,
            "embedding_dimensions": memory.embedding_dimensions,
            "embedding_generated_at": memory.embedding_generated_at,
            "source_session_id": memory.source_session_id,
            "source_message_ids": self._deserialize_payload(memory.source_message_ids_json),
            "occurred_at": memory.occurred_at,
            "last_seen_at": memory.last_seen_at,
            "expires_at": memory.expires_at,
            "created_at": memory.created_at,
            "updated_at": memory.updated_at,
        }


class ProfileMemoryRepository(object):
    def __init__(self, session):
        self.session = session

    def get_by_patient_and_key(self, patient_id, key):
        stmt = select(ProfileMemory).where(ProfileMemory.patient_id == patient_id, ProfileMemory.key == key)
        return self.session.execute(stmt).scalar_one_or_none()

    def create_memory(self, **memory_data):
        memory = ProfileMemory(**memory_data)
        self.session.add(memory)
        self.session.commit()
        self.session.refresh(memory)
        return memory

    def upsert_memory(self, patient_id, key, value, summary, confidence_score, source_session_id=None, last_seen_at=None):
        memory = self.get_by_patient_and_key(patient_id, key)
        current_time = last_seen_at or datetime.utcnow()
        if memory is None:
            return self.create_memory(
                patient_id=patient_id,
                key=key,
                value=value,
                summary=summary,
                confidence_score=confidence_score,
                source_session_id=source_session_id,
                last_seen_at=current_time,
            )

        if confidence_score > (memory.confidence_score + 0.05):
            memory.value = value
            memory.summary = summary
            memory.confidence_score = confidence_score
            memory.source_session_id = source_session_id
        memory.last_seen_at = current_time
        self.session.commit()
        self.session.refresh(memory)
        return memory

    def list_by_patient(self, patient_id, limit=50):
        stmt = (
            select(ProfileMemory)
            .where(ProfileMemory.patient_id == patient_id)
            .order_by(desc(ProfileMemory.updated_at), desc(ProfileMemory.created_at))
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()

    def to_read_model(self, memory):
        return {
            "id": memory.id,
            "patient_id": memory.patient_id,
            "key": memory.key,
            "value": memory.value,
            "summary": memory.summary,
            "confidence_score": memory.confidence_score,
            "source_session_id": memory.source_session_id,
            "last_seen_at": memory.last_seen_at,
            "created_at": memory.created_at,
            "updated_at": memory.updated_at,
        }


class MemoryExtractionJobRepository(object):
    def __init__(self, session):
        self.session = session

    def create_job(self, **job_data):
        job = MemoryExtractionJob(**job_data)
        self.session.add(job)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            stmt = select(MemoryExtractionJob).where(
                MemoryExtractionJob.session_id == job_data["session_id"],
                MemoryExtractionJob.from_sequence_no == job_data["from_sequence_no"],
                MemoryExtractionJob.to_sequence_no == job_data["to_sequence_no"],
            )
            return self.session.execute(stmt).scalar_one_or_none()
        self.session.refresh(job)
        return job

    def get_by_id(self, job_id):
        return self.session.get(MemoryExtractionJob, job_id)

    def list_pending(self, limit=20):
        now = datetime.utcnow()
        stmt = (
            select(MemoryExtractionJob)
            .where(
                MemoryExtractionJob.status == "pending",
                or_(MemoryExtractionJob.next_retry_at.is_(None), MemoryExtractionJob.next_retry_at <= now),
            )
            .order_by(asc(MemoryExtractionJob.created_at))
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()

    def claim_next_job(self):
        candidates = self.list_pending(limit=1)
        if not candidates:
            return None
        candidate = candidates[0]
        stmt = (
            update(MemoryExtractionJob)
            .where(MemoryExtractionJob.id == candidate.id, MemoryExtractionJob.status == "pending")
            .values(status="running", started_at=datetime.utcnow(), error_message=None)
        )
        result = self.session.execute(stmt)
        self.session.commit()
        if result.rowcount != 1:
            return None
        return self.get_by_id(candidate.id)

    def mark_completed(self, job_id):
        job = self.get_by_id(job_id)
        if job is None:
            return None
        job.status = "completed"
        job.finished_at = datetime.utcnow()
        job.error_message = None
        self.session.commit()
        self.session.refresh(job)
        return job

    def mark_retry_or_failed(self, job_id, error_message, retry_delay_seconds=None):
        job = self.get_by_id(job_id)
        if job is None:
            return None
        job.retry_count += 1
        job.error_message = error_message
        if job.retry_count >= job.max_retries or retry_delay_seconds is None:
            job.status = "failed"
            job.finished_at = datetime.utcnow()
            job.next_retry_at = None
        else:
            job.status = "pending"
            job.started_at = None
            job.next_retry_at = datetime.utcnow() + retry_delay_seconds
        self.session.commit()
        self.session.refresh(job)
        return job

    def to_read_model(self, job):
        return {
            "id": job.id,
            "patient_id": job.patient_id,
            "session_id": job.session_id,
            "from_sequence_no": job.from_sequence_no,
            "to_sequence_no": job.to_sequence_no,
            "status": job.status,
            "retry_count": job.retry_count,
            "max_retries": job.max_retries,
            "next_retry_at": job.next_retry_at,
            "error_message": job.error_message,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }
