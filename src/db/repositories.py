"""Incident / approval persistence and historical-incident candidates.

All queries are parameterized SQLAlchemy statements. Every historical query is filtered by repository in SQL,
so one repository's incidents can never be offered as context for another.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError

from src.db.client import session_scope
from src.db.models import Incident, RemediationApproval
from src.retrieval.history import HistoryCandidate, HistoryQuery, rank_lexical, to_prompt_records

HISTORY_CANDIDATE_LIMIT = 200  # newest eligible incidents per repository considered for ranking
HISTORY_ELIGIBLE_STATUSES = (
    "analysis_ready",
    "awaiting_approval",
    "pr_created",
    "pr_skipped_duplicate",
    "pr_failed",
    "remediation_rejected",
)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _aware(dt: datetime) -> datetime:
    """SQLite returns naive datetimes even for timezone=True columns; treat them as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def incident_to_dict(row: Incident) -> dict[str, Any]:
    return {
        "incident_id": str(row.id),
        "repo_name": row.repo_name,
        "fingerprint": row.fingerprint,
        "status": row.status,
        "status_reason": row.status_reason,
        "error_category": row.error_category,
        "error_message": row.error_message,
        "affected_file": row.affected_file,
        "quality_score": row.quality_score,
        "iterations": row.iterations,
        "analysis": row.root_cause_analysis,
        "suggested_patch": row.suggested_patch,
        "pr_url": row.pr_url,
        "pr_number": row.pr_number,
        "pr_branch": row.pr_branch,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def approval_to_dict(row: RemediationApproval) -> dict[str, Any]:
    return {
        "approval_id": str(row.id),
        "incident_id": str(row.incident_id),
        "action": row.action,
        "target_file": row.target_file,
        "patch_sha256": row.patch_sha256,
        "status": row.status,
        "reviewer": row.reviewer,
        "decision_note": row.decision_note,
        "created_at": _iso(row.created_at),
        "expires_at": _iso(_aware(row.expires_at)),
        "decided_at": _iso(row.decided_at),
    }


# ------------------------------------------------------------------ incidents


def create_incident(
    incident_id: uuid.UUID, repo_name: str, fingerprint: str, error_message: str, stack_trace: str
) -> tuple[dict[str, Any], bool]:
    """Insert a `processing` row. Idempotent per id: returns (row, created)."""
    try:
        with session_scope() as session:
            existing = session.get(Incident, incident_id)
            if existing is not None:
                return incident_to_dict(existing), False
            row = Incident(
                id=incident_id,
                repo_name=repo_name,
                fingerprint=fingerprint,
                error_message=error_message,
                stack_trace=stack_trace,
                status="processing",
            )
            session.add(row)
            session.flush()
            return incident_to_dict(row), True
    except IntegrityError:  # concurrent delivery with the same id won the insert race
        current = get_incident(incident_id)
        if current is None:
            raise
        return current, False


def update_incident(incident_id: uuid.UUID, **fields: Any) -> None:
    """Update named columns of an existing incident (attribute names from `Incident`)."""
    with session_scope() as session:
        row = session.get(Incident, incident_id)
        if row is None:
            raise LookupError(f"incident {incident_id} does not exist")
        for name, value in fields.items():
            if not hasattr(Incident, name):
                raise AttributeError(f"unknown incident field {name!r}")
            setattr(row, name, value)


def get_incident(incident_id: uuid.UUID) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(Incident, incident_id)
        return incident_to_dict(row) if row else None


# ------------------------------------------------------------------ history


def _root_cause_summary(analysis: dict[str, Any] | None) -> str:
    if not analysis:
        return ""
    try:
        return str(analysis["diagnostic_chain"]["primary_root_cause"]["technical_explanation"])
    except (KeyError, TypeError):
        return ""


def load_history_candidates(repo_name: str, exclude_id: str | None = None) -> list[HistoryCandidate]:
    """Newest eligible incidents of ONE repository (bounded), newest first."""
    stmt = (
        select(Incident)
        .where(Incident.repo_name == repo_name, Incident.status.in_(HISTORY_ELIGIBLE_STATUSES))
        .order_by(Incident.created_at.desc())
        .limit(HISTORY_CANDIDATE_LIMIT)
    )
    if exclude_id:
        stmt = stmt.where(Incident.id != uuid.UUID(exclude_id))
    with session_scope() as session:
        rows = list(session.scalars(stmt))
    return [
        HistoryCandidate(
            id=str(row.id),
            repo_name=row.repo_name,
            fingerprint=row.fingerprint,
            error_message=row.error_message[:2000],
            stack_trace=row.stack_trace[:8000],
            affected_file=row.affected_file,
            extra={
                "root_cause_summary": _root_cause_summary(row.root_cause_analysis)[:800],
                "suggested_patch": (row.suggested_patch or "")[:2000],
                "status": row.status,
                "pr_url": row.pr_url,
                "created_at": _iso(row.created_at),
            },
        )
        for row in rows
    ]


def find_similar_incidents(query: HistoryQuery, exclude_id: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Ranked, explained matches (strategy lexical-v1) for the prompt."""
    return to_prompt_records(rank_lexical(query, load_history_candidates(query.repo_name, exclude_id), limit))


def find_recent_pr(repo_name: str, fingerprint: str, hours: int = 24) -> str | None:
    """URL of a PR already opened for the same failure fingerprint within `hours`."""
    since = datetime.now(UTC) - timedelta(hours=hours)
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


# ------------------------------------------------------------------ approvals


def create_approval(incident_id: uuid.UUID, target_file: str, patch_sha256: str, ttl_hours: int) -> dict[str, Any]:
    """New pending approval; any older pending approval of the same incident is superseded."""
    now = datetime.now(UTC)
    with session_scope() as session:
        session.execute(
            update(RemediationApproval)
            .where(RemediationApproval.incident_id == incident_id, RemediationApproval.status == "pending")
            .values(status="superseded", decided_at=now)
        )
        row = RemediationApproval(
            id=uuid.uuid4(),
            incident_id=incident_id,
            target_file=target_file,
            patch_sha256=patch_sha256,
            status="pending",
            created_at=now,
            expires_at=now + timedelta(hours=ttl_hours),
        )
        session.add(row)
        session.flush()
        return approval_to_dict(row)


def get_approval(approval_id: uuid.UUID) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(RemediationApproval, approval_id)
        return approval_to_dict(row) if row else None


def get_pending_approval(incident_id: uuid.UUID) -> dict[str, Any] | None:
    stmt = select(RemediationApproval).where(
        RemediationApproval.incident_id == incident_id, RemediationApproval.status == "pending"
    )
    with session_scope() as session:
        row = session.scalars(stmt).first()
        return approval_to_dict(row) if row else None


def transition_approval(
    approval_id: uuid.UUID, from_status: str, to_status: str, reviewer: str | None = None, note: str | None = None
) -> bool:
    """Compare-and-set status change. Returns False if another request changed it first (no double execution)."""
    values: dict[str, Any] = {"status": to_status, "decided_at": datetime.now(UTC)}
    if reviewer is not None:
        values["reviewer"] = reviewer
    if note is not None:
        values["decision_note"] = note
    with session_scope() as session:
        result: CursorResult[Any] = session.execute(  # type: ignore[assignment]
            update(RemediationApproval)
            .where(RemediationApproval.id == approval_id, RemediationApproval.status == from_status)
            .values(**values)
        )
        return result.rowcount == 1
