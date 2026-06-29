"""Database helpers for medical knowledge tables."""

from app.db.database import Base

from . import models  # noqa: F401


def create_knowledge_tables(engine):
    Base.metadata.create_all(bind=engine)
