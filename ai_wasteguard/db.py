"""SQLAlchemy engine/session setup.

Works against either the default local SQLite database or an external
PostgreSQL database, selected purely by DATABASE_URL - no branching logic
elsewhere in the codebase should need to know which one is in use.
"""
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ai_wasteguard.config import get_database_url


class Base(DeclarativeBase):
    pass


def _make_engine(database_url: str | None = None):
    url = database_url or get_database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db(bind=None) -> None:
    """Create all tables. Intended for tests and local bootstrapping;
    real deployments should use Alembic migrations instead."""
    import ai_wasteguard.models  # noqa: F401  (register model metadata)

    Base.metadata.create_all(bind=bind or engine)


@contextmanager
def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
