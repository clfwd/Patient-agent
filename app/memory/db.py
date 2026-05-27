"""Database helpers for the long-term memory PostgreSQL store."""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


MemoryBase = declarative_base()


def get_memory_database_url():
    return os.getenv("MEMORY_DATABASE_URL")


def build_memory_engine(database_url=None):
    url = database_url or get_memory_database_url()
    if not url:
        return None

    engine_kwargs = {
        "future": True,
        "echo": False,
    }
    if url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            engine_kwargs["poolclass"] = StaticPool
    return create_engine(url, **engine_kwargs)


def build_memory_session_factory(engine):
    if engine is None:
        return None
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


_default_engine = build_memory_engine()
MemorySessionLocal = build_memory_session_factory(_default_engine)


def get_memory_embedding_dimensions(default=1024):
    raw = str(os.getenv("MEMORY_EMBEDDING_DIMENSIONS", default)).strip()
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        digits = "".join(ch for ch in raw if ch.isdigit())
        return max(int(digits or default), 1)


def init_memory_database(database_url=None):
    engine = build_memory_engine(database_url)
    if engine is None:
        return None, None
    from . import models  # noqa: F401

    MemoryBase.metadata.create_all(bind=engine)
    _ensure_memory_schema(engine)
    return engine, build_memory_session_factory(engine)


def _ensure_memory_schema(engine):
    if engine is None or engine.dialect.name != "postgresql":
        return

    embedding_dimensions = get_memory_embedding_dimensions()

    statements = [
        "CREATE EXTENSION IF NOT EXISTS vector",
        "ALTER TABLE event_memory ADD COLUMN IF NOT EXISTS search_text TEXT",
        "ALTER TABLE event_memory ADD COLUMN IF NOT EXISTS embedding_text TEXT",
        "ALTER TABLE event_memory ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(64)",
        "ALTER TABLE event_memory ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER",
        "ALTER TABLE event_memory ADD COLUMN IF NOT EXISTS embedding_vector VECTOR",
        "ALTER TABLE event_memory ADD COLUMN IF NOT EXISTS embedding_generated_at TIMESTAMP",
        (
            "ALTER TABLE event_memory "
            "ADD COLUMN IF NOT EXISTS search_tsv TSVECTOR "
            "GENERATED ALWAYS AS (to_tsvector('simple', COALESCE(search_text, ''))) STORED"
        ),
        "CREATE INDEX IF NOT EXISTS ix_event_memory_search_tsv_gin ON event_memory USING gin (search_tsv)",
        (
            "CREATE INDEX IF NOT EXISTS ix_event_memory_embedding_vector_hnsw "
            "ON event_memory USING hnsw ((embedding_vector::vector({0})) vector_cosine_ops) "
            "WHERE embedding_vector IS NOT NULL".format(embedding_dimensions)
        ),
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
