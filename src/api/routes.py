"""HTTP endpoints."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from src.api.auth import Principal, authenticate, rate_limited_reporter, require_role
from src.api.schemas import (
    ErrorResponse,
    HealthResponse,
    IncidentAccepted,
    IncidentRequest,
    IncidentResult,
    RemediationDecision,
)
from src.config import settings
from src.db.client import ping_database
from src.services import incident_service
from src.services.incident_service import DatabaseUnavailableError, IncidentConflictError, IncidentNotFoundError
from src.services.remediation_service import ApprovalError

logger = logging.getLogger(__name__)
router = APIRouter()

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid API key"},
    403: {"model": ErrorResponse, "description": "Role not allowed, repository not allowed, or self-approval"},
    503: {"model": ErrorResponse, "description": "Database unavailable or authentication not configured"},
}


@router.get("/healthz", response_model=HealthResponse, tags=["health"])
def healthz() -> HealthResponse:
    """Liveness: the process is up. Does not touch external services."""
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=HealthResponse, tags=["health"], responses={503: {"model": HealthResponse}})
def readyz() -> HealthResponse | JSONResponse:
    """Readiness: the database answers. Reports only ok/unavailable, never connection details."""
    try:
        ping_database()
    except SQLAlchemyError:
        body = HealthResponse(status="unavailable", checks={"database": "unavailable"})
        return JSONResponse(status_code=503, content=body.model_dump())
    return HealthResponse(status="ready", checks={"database": "ok"})


@router.post(
    "/webhook/incident",
    response_model=IncidentAccepted | IncidentResult,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["incidents"],
    responses={
        **_ERRORS,
        200: {
            "model": IncidentResult,
            "description": "Synchronous result (wait=true) or existing incident for a repeated incident_id",
        },
        409: {"model": ErrorResponse},
        429: {"model": ErrorResponse, "description": "Per-identity rate limit exceeded (see Retry-After)"},
    },
)
def submit_incident(
    payload: IncidentRequest,
    background_tasks: BackgroundTasks,
    principal: Annotated[Principal, Depends(rate_limited_reporter)],
    wait: bool = Query(False, description="Run the analysis synchronously and return the full result"),
) -> IncidentAccepted | JSONResponse:
    """Accept an incident report (roles: reporter, reviewer, admin). Runs in the background unless `wait=true`."""
    if not settings.is_repository_allowed(payload.repo_name):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "repository is not in ALLOWED_REPOSITORIES")
    incident_id = payload.incident_id or uuid.uuid4()
    try:
        row, created = incident_service.submit_incident(
            incident_id, payload.repo_name, payload.error_message, payload.stack_trace, submitted_by=principal.name
        )
    except IncidentConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except DatabaseUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable") from exc

    if not created:
        logger.info("repeated delivery for incident %s ignored", incident_id)
        return JSONResponse(status_code=200, content=IncidentResult(**row).model_dump(mode="json"))
    if wait:
        try:
            result = incident_service.run_incident_pipeline(
                incident_id, payload.repo_name, payload.error_message, payload.stack_trace
            )
        except DatabaseUnavailableError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable") from exc
        return JSONResponse(status_code=200, content=IncidentResult(**result).model_dump(mode="json"))
    background_tasks.add_task(
        incident_service.process_incident_in_background,
        incident_id,
        payload.repo_name,
        payload.error_message,
        payload.stack_trace,
    )
    return IncidentAccepted(incident_id=str(incident_id), status="processing")


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentResult,
    dependencies=[Depends(authenticate)],
    tags=["incidents"],
    responses={**_ERRORS, 404: {"model": ErrorResponse}},
)
def read_incident(incident_id: uuid.UUID) -> IncidentResult:
    try:
        row = incident_service.get_incident_with_approval(incident_id)
    except DatabaseUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable") from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "incident not found")
    return IncidentResult(**row)


@router.post(
    "/incidents/{incident_id}/remediation/decision",
    response_model=IncidentResult,
    tags=["remediation"],
    responses={**_ERRORS, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def decide_remediation(
    incident_id: uuid.UUID,
    body: RemediationDecision,
    principal: Annotated[Principal, Depends(require_role("reviewer"))],
) -> IncidentResult:
    """Approve or reject the PR proposed for an incident (roles: reviewer, admin).

    The request must name the pending approval and echo the SHA-256 of the proposed patch, so a decision can
    only apply to the exact change the reviewer saw. The reviewer is the authenticated identity, and it may not
    be the identity that submitted the incident (four-eyes rule). Decisions are final; a repeat returns 409.
    """
    try:
        row = incident_service.decide_remediation(
            incident_id, body.approval_id, body.patch_sha256, body.decision == "approve", principal.name, body.note
        )
    except IncidentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "incident not found") from exc
    except ApprovalError as exc:
        raise HTTPException(exc.http_status, str(exc)) from exc
    except DatabaseUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable") from exc
    return IncidentResult(**row)
