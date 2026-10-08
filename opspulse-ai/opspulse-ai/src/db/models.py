"""SQLAlchemy models for Neon PostgreSQL (Developer 2)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSONType = JSON().with_variant(JSONB(), "postgresql")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incidents_repo_fingerprint", "repo_name", "fingerprint"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    repo_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stack_trace: Mapped[str] = mapped_column(Text, nullable=False, default="")
    affected_file: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, index=True)
    root_cause_analysis: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType, nullable=True)
    suggested_patch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # processing | needs_review | pr_created | pr_skipped_duplicate | pr_failed | failed
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="processing")
    pr_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    pr_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pr_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
