"""ORM models for local medical knowledge documents and chunks."""

import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.db.database import Base
from app.db.models import FlexibleDateTime


def _uuid():
    return str(uuid.uuid4())


class KnowledgeTimestampMixin(object):
    created_at = Column(FlexibleDateTime(), default=datetime.utcnow, server_default=func.now(), nullable=False)
    updated_at = Column(
        FlexibleDateTime(),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )


class MedicalKnowledgeDocument(KnowledgeTimestampMixin, Base):
    __tablename__ = "medical_knowledge_documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    title = Column(String(255), nullable=False)
    source = Column(String(255), nullable=False)
    source_type = Column(String(64), nullable=False, default="manual")
    content = Column(Text, nullable=False)
    metadata_json = Column(Text)

    chunks = relationship(
        "MedicalKnowledgeChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="MedicalKnowledgeChunk.chunk_index",
    )


class MedicalKnowledgeChunk(Base):
    __tablename__ = "medical_knowledge_chunks"

    id = Column(String(36), primary_key=True, default=_uuid)
    document_id = Column(String(36), ForeignKey("medical_knowledge_documents.id"), index=True, nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)
    metadata_json = Column(Text)
    search_text = Column(Text, nullable=False)
    created_at = Column(FlexibleDateTime(), default=datetime.utcnow, server_default=func.now(), nullable=False)

    document = relationship("MedicalKnowledgeDocument", back_populates="chunks")
