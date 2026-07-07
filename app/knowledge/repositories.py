"""Repositories for local medical knowledge documents and chunks."""

import json

from sqlalchemy import asc, desc, select
from sqlalchemy.orm import joinedload

from .models import MedicalKnowledgeChunk, MedicalKnowledgeDocument


class MedicalKnowledgeRepository(object):
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _serialize_metadata(metadata):
        if metadata in (None, ""):
            return None
        return json.dumps(metadata, ensure_ascii=False, default=str)

    @staticmethod
    def _deserialize_metadata(metadata_json):
        if not metadata_json:
            return None
        try:
            return json.loads(metadata_json)
        except (TypeError, ValueError):
            return {"raw": metadata_json}

    def create_document(self, title, source, content, source_type="manual", metadata=None):
        document = MedicalKnowledgeDocument(
            title=title,
            source=source,
            source_type=source_type,
            content=content,
            metadata_json=self._serialize_metadata(metadata),
        )
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def create_chunks(self, document_id, chunks):
        created = []
        for index, item in enumerate(chunks):
            if isinstance(item, dict):
                content = item.get("content") or ""
                metadata = item.get("metadata")
                search_text = item.get("search_text") or content
                chunk_index = item.get("chunk_index", index)
            else:
                content = str(item)
                metadata = None
                search_text = content
                chunk_index = index
            chunk = MedicalKnowledgeChunk(
                document_id=document_id,
                chunk_index=chunk_index,
                content=content,
                metadata_json=self._serialize_metadata(metadata),
                search_text=search_text,
            )
            self.session.add(chunk)
            created.append(chunk)
        self.session.commit()
        for chunk in created:
            self.session.refresh(chunk)
        return created

    def list_chunks(self, limit=200):
        stmt = (
            select(MedicalKnowledgeChunk)
            .options(joinedload(MedicalKnowledgeChunk.document))
            .order_by(desc(MedicalKnowledgeChunk.created_at), asc(MedicalKnowledgeChunk.chunk_index))
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()

    def to_search_result(self, chunk):
        document = chunk.document
        return {
            "content": chunk.content,
            "title": document.title,
            "source": document.source,
            "document_id": document.id,
            "chunk_id": chunk.id,
            "source_type": document.source_type,
            "metadata": self._deserialize_metadata(chunk.metadata_json),
        }
