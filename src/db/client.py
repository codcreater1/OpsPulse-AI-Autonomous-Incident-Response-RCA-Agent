"""Engine and transaction management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.config import ConfigError, settings


def normalize_database_url(url: str) -> str:
    """Neon/Heroku style `postgres(ql)://` URLs -> SQLAlchemy psycopg2 driver URL."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    if not settings.database_url:
        raise ConfigError("DATABASE_URL is not set")
    url = normalize_database_url(settings.database_url)
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("postgresql"):
        # Neon scales to zero and drops idle connections: validate and recycle aggressively, fail fast.
        kwargs.update(
            pool_recycle=240, pool_size=5, max_overflow=5, pool_timeout=10, connect_args={"connect_timeout": 10}
        )
    return create_engine(url, **kwargs)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """One transaction: commit on success, roll back and re-raise on any error."""
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def ping_database() -> None:
    """Raise SQLAlchemyError if the database cannot answer a trivial query."""
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
