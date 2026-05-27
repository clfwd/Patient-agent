"""ORM models for long-term event and profile memories."""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.types import Text as TextType
from sqlalchemy.types import TypeDecorator, UserDefinedType

from .db import MemoryBase


def _uuid():
    return str(uuid.uuid4())


class _PgVectorType(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw):
        return "VECTOR"


class VectorTextType(TypeDecorator):
    """Store pgvector values in PostgreSQL and plain text elsewhere."""

    impl = TextType
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PgVectorType())
        return dialect.type_descriptor(TextType())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        values = [float(item) for item in value]
        return "[{0}]".format(",".join("{0:.12g}".format(item) for item in values))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, list):
            return [float(item) for item in value]
        text = str(value).strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1].strip()
        if not text:
            return []
        return [float(item.strip()) for item in text.split(",") if item.strip()]


class EventMemory(MemoryBase):
    __tablename__ = "event_memory"

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), index=True, nullable=False)
    category = Column(String(64), index=True, nullable=False)
    summary = Column(Text, nullable=False)
    payload_json = Column(Text)
    confidence_score = Column(Float, nullable=False)
    search_text = Column(Text)
    embedding_text = Column(Text)
    embedding_model = Column(String(64), index=True)
    embedding_dimensions = Column(Integer)
    embedding_vector = Column(VectorTextType())
    embedding_generated_at = Column(DateTime)
    source_session_id = Column(String(36), index=True)
    source_message_ids_json = Column(Text)
    occurred_at = Column(DateTime)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )


class ProfileMemory(MemoryBase):
    __tablename__ = "profile_memory"
    __table_args__ = (UniqueConstraint("patient_id", "key", name="uq_profile_memory_patient_key"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), index=True, nullable=False)
    key = Column(String(64), nullable=False)
    value = Column(String(128), nullable=False)
    summary = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=False)
    source_session_id = Column(String(36), index=True)
    last_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )


class MemoryExtractionJob(MemoryBase):
    __tablename__ = "memory_extraction_job"
    __table_args__ = (
        UniqueConstraint("session_id", "from_sequence_no", "to_sequence_no", name="uq_memory_job_session_window"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    patient_id = Column(String(36), index=True, nullable=False)
    session_id = Column(String(36), index=True, nullable=False)
    from_sequence_no = Column(Integer, nullable=False)
    to_sequence_no = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="pending", index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    next_retry_at = Column(DateTime, index=True)
    error_message = Column(Text)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
