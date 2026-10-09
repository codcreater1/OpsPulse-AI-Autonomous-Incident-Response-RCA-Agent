"""HTTP endpoints."""

from __future__ import annotations

import hmac
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from sqlalchemy.exc import SQLAlchemyError

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

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid API key"},
    503: {"model": ErrorResponse, "description": "Database unavailable or authentication not configured"},
}


def require_api_key(provided: Annotated[str | None, Security(_api_key_header)]) -> None:
    """Fail closed: without API_KEY the API refuses requests unless ALLOW_UNAUTHENTICATED=true (local dev)."""
    if not settings.api_key:
        if settings.allow_unauthenticated:
            return
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "API authentication is not configured (set API_KEY)")
    if not provided or not hmac.compare_digest(provided.encode(), settings.api_key.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API key")


Authenticated = Depends(require_api_key)


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
    dependencies=[Authenticated],
    tags=["incidents"],
    responses={
        **_ERRORS,
        200: {
            "model": IncidentResult,
            "description": "Synchronous result (wait=true) or existing incident for a repeated incident_id",
        },
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def submit_incident(
    payload: IncidentRequest,
    background_tasks: BackgroundTasks,
    wait: bool = Query(False, description="Run the analysis synchronously and return the full result"),
) -> IncidentAccepted | JSONResponse:
    """Accept an incident report. Analysis runs in the background unless `wait=true`."""
    if not settings.is_repository_allowed(payload.repo_name):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "repository is not in ALLOWED_REPOSITORIES")
    incident_id = payload.incident_id or uuid.uuid4()
    try:
        row, created = incident_service.submit_incident(
            incident_id, payload.repo_name, payload.error_message, payload.stack_trace
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
    dependencies=[Authenticated],
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
    dependencies=[Authenticated],
    tags=["remediation"],
    responses={**_ERRORS, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def decide_remediation(incident_id: uuid.UUID, body: RemediationDecision) -> IncidentResult:
    """Approve or reject the PR proposed for an incident.

    The request must name the pending approval and echo the SHA-256 of the proposed patch, so a decision can
    only apply to the exact change the reviewer saw. Decisions are final; a second decision returns 409.
    """
    try:
        row = incident_service.decide_remediation(
            incident_id, body.approval_id, body.patch_sha256, body.decision == "approve", body.reviewer, body.note
        )
    except IncidentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "incident not found") from exc
    except ApprovalError as exc:
        raise HTTPException(exc.http_status, str(exc)) from exc
    except DatabaseUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable") from exc
    return IncidentResult(**row)
