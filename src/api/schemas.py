"""Public API contracts. Kept separate from the graph state and the database model on purpose."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

IncidentStatus = Literal[
    "processing",
    "failed",
    "needs_review",
    "analysis_ready",
    "awaiting_approval",
    "remediation_rejected",
    "pr_created",
    "pr_skipped_duplicate",
    "pr_failed",
]


class IncidentRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "repo_name": "your-org/your-repo",
                "error_message": "TypeError: 'NoneType' object is not subscriptable",
                "stack_trace": 'Traceback (most recent call last):\n  File "/app/src/app.py", line 6, in '
                "load_user\n    name = profile[\"name\"]\nTypeError: 'NoneType' object is not "
                "subscriptable",
            }
        },
    )

    repo_name: str = Field(
        ...,
        min_length=3,
        max_length=201,
        pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$",
        description="GitHub 'owner/repo'. Must be listed in ALLOWED_REPOSITORIES.",
    )
    error_message: str = Field(..., min_length=1, max_length=20_000)
    stack_trace: str = Field("", max_length=100_000)
    incident_id: uuid.UUID | None = Field(
        None, description="Optional client-generated id. Re-sending the same id is idempotent (no re-analysis)."
    )

    @field_validator("repo_name")
    @classmethod
    def _normalize_repo(cls, value: str) -> str:
        if any(part in {".", ".."} for part in value.split("/")):
            raise ValueError("invalid repository identifier")
        return value.lower()  # GitHub repository names are case-insensitive


class IncidentAccepted(BaseModel):
    incident_id: str
    status: IncidentStatus


class PendingApproval(BaseModel):
    approval_id: str
    action: str
    target_file: str
    patch_sha256: str = Field(description="SHA-256 of suggested_patch; must be echoed back to approve")
    expires_at: str


class RemediationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: uuid.UUID
    patch_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    decision: Literal["approve", "reject"]
    reviewer: str = Field(
        ..., min_length=1, max_length=200, description="Self-declared reviewer name (recorded, not authenticated)"
    )
    note: str | None = Field(None, max_length=2000)


class IncidentResult(BaseModel):
    incident_id: str
    repo_name: str
    status: IncidentStatus
    status_reason: str | None = None
    error_category: str | None = Field(None, description="Failure / partial-result category (src/errors.py)")
    error_message: str
    affected_file: str | None = None
    quality_score: float = Field(description="Deterministic rubric score (0-1). Not a probability of correctness.")
    iterations: int = Field(description="Number of completed LLM analysis attempts")
    analysis: dict[str, Any] | None = Field(None, description="Structured RCA plus the evaluator's check breakdown")
    suggested_patch: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None
    pr_branch: str | None = None
    pending_approval: PendingApproval | None = Field(
        None, description="Present while a proposed PR waits for a human decision"
    )
    created_at: str | None = None
    updated_at: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok", "ready", "unavailable"]
    checks: dict[str, str] = Field(default_factory=dict)
