"""数据库引擎、会话工厂与建表初始化。"""

from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from .config import get_database_url


Base = declarative_base()


def build_engine(database_url=None):
    """创建 SQLAlchemy Engine。"""
    url = database_url or get_database_url()

    engine_kwargs = {
        "future": True,
        "echo": False,
    }

    if url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            engine_kwargs["poolclass"] = StaticPool

    return create_engine(url, **engine_kwargs)


def build_session_factory(engine):
    """基于 Engine 创建会话工厂。"""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


engine = build_engine()
SessionLocal = build_session_factory(engine)


def create_all_tables(engine_override=None):
    """初始化所有 ORM 表。"""
    from . import models  # noqa: F401

    target_engine = engine_override or engine
    Base.metadata.create_all(bind=target_engine)


def normalize_sqlite_datetime_columns(engine_override=None):
    """兼容旧版 SQLite 数据中的 ISO 时间文本格式。

    早期手写 sqlite3 版本会把时间存成 `2026-04-19T12:51:15.104647`，
    而 SQLAlchemy 的 SQLite DateTime 更稳定的读取格式是带空格的形式。
    这里在启动时做一次轻量修正，保证旧库可继续被 ORM 正常读取。
    """

    target_engine = engine_override or engine
    if target_engine.dialect.name != "sqlite":
        return

    statements = [
        "UPDATE patients SET created_at = REPLACE(created_at, 'T', ' ') WHERE created_at LIKE '%T%'",
        "UPDATE patients SET updated_at = REPLACE(updated_at, 'T', ' ') WHERE updated_at LIKE '%T%'",
        "UPDATE medical_records SET created_at = REPLACE(created_at, 'T', ' ') WHERE created_at LIKE '%T%'",
        "UPDATE medical_records SET updated_at = REPLACE(updated_at, 'T', ' ') WHERE updated_at LIKE '%T%'",
        "UPDATE visits SET visit_time = REPLACE(visit_time, 'T', ' ') WHERE visit_time LIKE '%T%'",
        "UPDATE visits SET created_at = REPLACE(created_at, 'T', ' ') WHERE created_at LIKE '%T%'",
        "UPDATE visits SET updated_at = REPLACE(updated_at, 'T', ' ') WHERE updated_at LIKE '%T%'",
    ]

    with target_engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def init_database(database_url=None):
    """初始化数据库，并返回 engine 和会话工厂。"""
    db_engine = build_engine(database_url)
    create_all_tables(db_engine)
    normalize_sqlite_datetime_columns(db_engine)
    return db_engine, build_session_factory(db_engine)


@contextmanager
def get_session(session_factory=None):
    """提供自动提交/回滚的数据库会话上下文。"""
    factory = session_factory or SessionLocal
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
