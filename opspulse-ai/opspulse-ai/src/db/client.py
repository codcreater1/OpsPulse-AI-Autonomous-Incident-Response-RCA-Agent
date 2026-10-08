"""Engine/session management and persistence helpers for Neon (Developer 2)."""
from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Dict, Iterator, List, Optional

from sqlalchemy import Engine, create_engine, or_, select
from sqlalchemy.orm import Session, sessionmaker

from src.agent.parsing import compute_fingerprint
from src.agent.state import IncidentState
from src.config import settings
from src.db.models import Base, Incident

logger = logging.getLogger(__name__)


def normalize_database_url(url: str) -> str:
    """Neon gives `postgresql://...`; make sure SQLAlchemy uses the psycopg2 driver."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = settings.neon_database_url
    if not url:
        raise RuntimeError("NEON_DATABASE_URL is not set")
    url = normalize_database_url(url)
    kwargs: Dict[str, Any] = {"pool_pre_ping": True, "future": True}
    if url.startswith("postgresql"):
        # Neon scales to zero and drops idle connections: validate + recycle aggressively.
        kwargs.update(pool_recycle=240, pool_size=5, max_overflow=5, connect_args={"connect_timeout": 15})
    return create_engine(url, **kwargs)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create the `incidents` table if it does not exist."""
    Base.metadata.create_all(get_engine())


def reset_engine_cache() -> None:
    """Test helper: forget the cached engine / session factory."""
    get_engine.cache_clear()
    _session_factory.cache_clear()


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _root_cause_summary(analysis: Optional[Dict[str, Any]]) -> str:
    try:
        return str(analysis["diagnostic_chain"]["primary_root_cause"]["technical_explanation"])
    except (KeyError, TypeError):
        return ""


def incident_to_dict(row: Incident) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "fingerprint": row.fingerprint,
        "repo_name": row.repo_name,
        "error_message": row.error_message,
        "affected_file": row.affected_file,
        "root_cause_analysis": row.root_cause_analysis,
        "suggested_patch": row.suggested_patch,
        "confidence_score": row.confidence_score,
        "iterations": row.iterations,
        "status": row.status,
        "pr_url": row.pr_url,
        "pr_number": row.pr_number,
        "pr_branch": row.pr_branch,
        "failure_reason": row.failure_reason,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def save_incident_to_db(
    state: IncidentState,
    *,
    incident_id: Optional[uuid.UUID] = None,
    status: str = "needs_review",
    pr_url: Optional[str] = None,
    pr_number: Optional[int] = None,
    pr_branch: Optional[str] = None,
    failure_reason: Optional[str] = None,
) -> uuid.UUID:
    """Insert or update (upsert by id) an incident row from the graph state; returns its id."""
    fingerprint = compute_fingerprint(state["repo_name"], state["error_message"], state["stack_trace"])
    with session_scope() as session:
        row = session.get(Incident, incident_id) if incident_id else None
        if row is None:
            row = Incident(id=incident_id or uuid.uuid4(), fingerprint=fingerprint, repo_name=state["repo_name"])
            session.add(row)
        row.fingerprint = fingerprint
        row.repo_name = state["repo_name"]
        row.error_message = state["error_message"]
        row.stack_trace = state["stack_trace"]
        row.affected_file = state.get("affected_file")
        row.root_cause_analysis = state.get("root_cause_analysis")
        row.suggested_patch = state.get("suggested_patch")
        row.confidence_score = float(state.get("confidence_score") or 0.0)
        row.iterations = int(state.get("iterations") or 0)
        row.status = status
        if pr_url is not None:
            row.pr_url = pr_url
        if pr_number is not None:
            row.pr_number = pr_number
        if pr_branch is not None:
            row.pr_branch = pr_branch
        row.failure_reason = failure_reason
        session.flush()
        return row.id


def get_incident(incident_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    with session_scope() as session:
        row = session.get(Incident, incident_id)
        return incident_to_dict(row) if row else None


def find_similar_incidents(
    repo_name: str,
    fingerprint: str,
    affected_file: Optional[str],
    *,
    exclude_id: Optional[uuid.UUID] = None,
    min_confidence: float = 0.6,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Historical memory: exact fingerprint matches first, then same-file incidents."""
    conditions = [Incident.fingerprint == fingerprint]
    if affected_file:
        conditions.append(Incident.affected_file == affected_file)
    stmt = (
        select(Incident)
        .where(Incident.repo_name == repo_name, or_(*conditions), Incident.confidence_score >= min_confidence)
        .order_by(Incident.created_at.desc())
        .limit(limit * 3)
    )
    if exclude_id is not None:
        stmt = stmt.where(Incident.id != exclude_id)
    with session_scope() as session:
        rows = list(session.scalars(stmt))
    results: List[Dict[str, Any]] = []
    for row in rows:
        results.append(
            {
                "id": str(row.id),
                "match_type": "exact" if row.fingerprint == fingerprint else "same_file",
                "error_message": row.error_message[:500],
                "affected_file": row.affected_file,
                "root_cause_summary": _root_cause_summary(row.root_cause_analysis)[:800],
                "suggested_patch": (row.suggested_patch or "")[:2000],
                "confidence_score": row.confidence_score,
                "status": row.status,
                "pr_url": row.pr_url,
                "created_at": _iso(row.created_at),
            }
        )
    results.sort(key=lambda r: 0 if r["match_type"] == "exact" else 1)  # stable: keeps recency order
    return results[:limit]


def find_recent_pr(repo_name: str, fingerprint: str, hours: int = 24) -> Optional[str]:
    """URL of a PR already opened for the same fingerprint within `hours` (duplicate-PR guard)."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(Incident.pr_url)
        .where(
            Incident.repo_name == repo_name,
            Incident.fingerprint == fingerprint,
            Incident.pr_url.is_not(None),
            Incident.created_at >= since,
        )
        .order_by(Incident.created_at.desc())
        .limit(1)
    )
    with session_scope() as session:
        return session.scalars(stmt).first()
