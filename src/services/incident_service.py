"""Application layer: incident intake, graph execution, persistence, remediation and approvals.

Incident status lifecycle (persisted in `incidents.status`; `error_category` says why, see src/errors.py):

    processing ──► failed                 no usable analysis (LLM provider error, unexpected exception)
              ├──► needs_review           gate not passed (budget exhausted / insufficient evidence / no source)
              │                           or the patch violated remediation policy
              ├──► analysis_ready         gate passed; PR not attempted (remediation disabled / no token)
              ├──► awaiting_approval ──► pr_created | pr_skipped_duplicate | pr_failed   (approved)
              │                     └──► remediation_rejected                             (rejected)
              ├──► pr_created             (only when REQUIRE_REMEDIATION_APPROVAL=false)
              ├──► pr_skipped_duplicate
              └──► pr_failed

Side effects (DB writes, PR creation) happen here, never inside graph nodes, so a retried analysis attempt
cannot open a PR. Workflow state is not checkpointed: the graph runs to completion within one request and
everything needed to resume (the analysis, the patch, the pending approval) is persisted in PostgreSQL.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import timedelta
from functools import lru_cache
from typing import Any, cast

from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.exc import SQLAlchemyError

from src import metrics
from src.agent.graph import build_graph
from src.agent.parsing import compute_fingerprint
from src.agent.state import IncidentState, initial_state
from src.config import settings
from src.db import repositories
from src.errors import ErrorCategory
from src.integrations import github
from src.integrations.observability import build_run_config, flush_traces, incident_trace
from src.logging_config import incident_id_var, redact
from src.services import remediation_service
from src.services.remediation_service import ApprovalForbiddenError, ProposedFix, RemediationOutcome

logger = logging.getLogger(__name__)


class DatabaseUnavailableError(RuntimeError):
    pass


class IncidentConflictError(ValueError):
    """The client reused an incident id for a different repository."""


class IncidentNotFoundError(LookupError):
    pass


@lru_cache(maxsize=1)
def get_graph() -> CompiledStateGraph:
    return build_graph(github.fetch_source_context, repositories.find_similar_incidents)


def submit_incident(
    incident_id: uuid.UUID, repo_name: str, error_message: str, stack_trace: str, submitted_by: str | None = None
) -> tuple[dict[str, Any], bool]:
    """Persist a new `processing` incident, or return the existing one for a repeated delivery."""
    fingerprint = compute_fingerprint(repo_name, error_message, stack_trace)
    try:
        row, created = repositories.create_incident(
            incident_id, repo_name, fingerprint, error_message, stack_trace, submitted_by
        )
    except SQLAlchemyError as exc:
        logger.error("database unavailable while creating incident: %s", type(exc).__name__)
        raise DatabaseUnavailableError("database unavailable") from exc
    if not created and row["repo_name"] != repo_name:
        raise IncidentConflictError("incident_id already used for a different repository")
    return row, created


def _final_status(final: IncidentState) -> tuple[str, str, str | None]:
    if final["workflow_status"] == "failed":
        return "failed", final["error"] or "analysis failed", final["error_category"]
    decision = ((final["root_cause_analysis"] or {}).get("evaluation") or {}).get("decision")
    category = final["error_category"] or ErrorCategory.RETRY_BUDGET_EXHAUSTED.value
    return "needs_review", decision or "analysis did not pass the quality gate", category


def _fix_from_state(incident_id: uuid.UUID, fingerprint: str, final: IncidentState) -> ProposedFix:
    return ProposedFix(
        incident_id=incident_id,
        repo_name=final["repo_name"],
        fingerprint=fingerprint,
        target_file=final["affected_file"],
        patch=final["suggested_patch"],
        analysis=final["root_cause_analysis"] or {},
        quality_score=final["quality_score"],
        iterations=final["iterations"],
    )


def _outcome_fields(outcome: RemediationOutcome) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "status": outcome.status,
        "status_reason": redact(outcome.reason),
        "error_category": outcome.category.value if outcome.category else None,
    }
    if outcome.pr_url:
        fields.update(pr_url=outcome.pr_url, pr_number=outcome.pr_number, pr_branch=outcome.branch)
    return fields


def run_incident_pipeline(
    incident_id: uuid.UUID, repo_name: str, error_message: str, stack_trace: str
) -> dict[str, Any]:
    """Run the graph, persist the outcome, optionally propose/open a PR. Returns the stored incident.

    Raises DatabaseUnavailableError when the outcome cannot be persisted; no PR is attempted in that case,
    because the duplicate-PR guard and the approval record depend on the database.
    """
    token = incident_id_var.set(str(incident_id))
    fingerprint = compute_fingerprint(repo_name, error_message, stack_trace)
    started = time.perf_counter()
    try:
        with incident_trace(str(incident_id), repo_name, fingerprint) as trace:
            result = _run(incident_id, repo_name, error_message, stack_trace, fingerprint)
            metrics.PIPELINE_SECONDS.observe(time.perf_counter() - started)
            metrics.record_incident(result["status"], result["error_category"])
            trace.update(
                output={"status": result["status"], "quality_score": result["quality_score"]},
                metadata={"attempts": result["iterations"], "error_category": result["error_category"]},
                error=result["error_category"] if result["status"] == "failed" else None,
            )
            return result
    finally:
        flush_traces()
        incident_id_var.reset(token)


def _run(
    incident_id: uuid.UUID, repo_name: str, error_message: str, stack_trace: str, fingerprint: str
) -> dict[str, Any]:
    state = initial_state(str(incident_id), error_message, stack_trace, repo_name)
    try:
        final = cast(
            IncidentState, get_graph().invoke(state, config=build_run_config(str(incident_id), repo_name, fingerprint))
        )
    except Exception:  # background-job boundary: any crash is logged and recorded as `failed`, never swallowed
        logger.exception("workflow crashed")
        _persist_or_raise(
            incident_id,
            status="failed",
            status_reason="internal error during analysis",
            error_category=ErrorCategory.INTERNAL_ERROR.value,
        )
        return _load(incident_id)

    _persist_or_raise(
        incident_id,
        error_message=final["error_message"],
        stack_trace=final["stack_trace"],
        affected_file=final["affected_file"],
        root_cause_analysis={**(final["root_cause_analysis"] or {}), "attempts": final["attempts"]},
        suggested_patch=final["suggested_patch"],
        quality_score=final["quality_score"],
        iterations=final["iterations"],
    )
    if final["quality_gate_passed"]:
        try:
            outcome = remediation_service.remediate(_fix_from_state(incident_id, fingerprint, final))
        except SQLAlchemyError as exc:
            logger.error("database unavailable during remediation: %s", type(exc).__name__)
            raise DatabaseUnavailableError("database unavailable") from exc
        _persist_or_raise(incident_id, **_outcome_fields(outcome))
    else:
        status, reason, category = _final_status(final)
        _persist_or_raise(incident_id, status=status, status_reason=redact(reason), error_category=category)
    result = _load(incident_id)
    logger.info(
        "incident finished: status=%s score=%.2f attempts=%d",
        result["status"],
        result["quality_score"],
        result["iterations"],
    )
    return result


def process_incident_in_background(
    incident_id: uuid.UUID, repo_name: str, error_message: str, stack_trace: str
) -> None:
    """BackgroundTasks entry point: failures are logged; the row stays `processing` if the DB is down."""
    try:
        run_incident_pipeline(incident_id, repo_name, error_message, stack_trace)
    except DatabaseUnavailableError:
        logger.error("incident %s outcome could not be persisted", incident_id)


def list_incidents(
    status: str | None, repo_name: str | None, limit: int, cursor: str | None
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        return repositories.list_incidents(status, repo_name, limit, cursor)
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError("database unavailable") from exc


def get_incident_with_approval(incident_id: uuid.UUID) -> dict[str, Any] | None:
    try:
        row = repositories.get_incident(incident_id)
        if row is None:
            return None
        row["pending_approval"] = repositories.get_pending_approval(incident_id)
        return row
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError("database unavailable") from exc


def decide_remediation(
    incident_id: uuid.UUID, approval_id: uuid.UUID, patch_sha256: str, approve: bool, reviewer: str, note: str | None
) -> dict[str, Any]:
    """Apply a human approval/rejection. Raises IncidentNotFoundError, ApprovalError, DatabaseUnavailableError."""
    token = incident_id_var.set(str(incident_id))
    try:
        row = repositories.get_incident(incident_id)
        if row is None:
            raise IncidentNotFoundError("incident not found")
        fix = ProposedFix(
            incident_id=incident_id,
            repo_name=row["repo_name"],
            fingerprint=row["fingerprint"],
            target_file=row["affected_file"],
            patch=row["suggested_patch"],
            analysis=row["analysis"] or {},
            quality_score=row["quality_score"],
            iterations=row["iterations"],
        )
        if not settings.allow_self_approval and row["submitted_by"] and row["submitted_by"] == reviewer:
            raise ApprovalForbiddenError("the identity that submitted an incident may not decide its remediation")
        outcome = remediation_service.decide(fix, approval_id, patch_sha256, approve, reviewer, note)
        logger.info("remediation decision applied: approve=%s -> %s", approve, outcome.status)
        _persist_or_raise(incident_id, **_outcome_fields(outcome))
        metrics.record_decision(approve)
        metrics.record_incident(outcome.status, outcome.category.value if outcome.category else None)
        return _load(incident_id)
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError("database unavailable") from exc
    finally:
        flush_traces()
        incident_id_var.reset(token)


def recover_interrupted_incidents() -> int:
    """Fail incidents left in `processing` by a process that died (BackgroundTasks are not durable)."""
    try:
        return repositories.fail_stale_processing(
            timedelta(minutes=settings.stale_processing_minutes),
            "analysis was interrupted (process stopped); re-submit the incident",
            ErrorCategory.INTERRUPTED.value,
        )
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError("database unavailable") from exc


def _persist_or_raise(incident_id: uuid.UUID, **fields: Any) -> None:
    try:
        repositories.update_incident(incident_id, **fields)
    except SQLAlchemyError as exc:
        logger.error("database unavailable while saving incident: %s", type(exc).__name__)
        raise DatabaseUnavailableError("database unavailable") from exc


def _load(incident_id: uuid.UUID) -> dict[str, Any]:
    row = get_incident_with_approval(incident_id)
    if row is None:
        raise DatabaseUnavailableError("incident row disappeared")
    return row
