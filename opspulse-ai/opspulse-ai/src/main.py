"""FastAPI webhook server (Developer 2): ingest -> graph -> Neon -> GitHub PR."""
from __future__ import annotations

import hmac
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from src.agent.graph import ops_pulse_graph
from src.agent.parsing import compute_fingerprint
from src.agent.state import IncidentState, initial_state
from src.agent.tracing import build_run_config, flush_langfuse
from src.config import settings
from src.db.client import find_recent_pr, get_incident, init_db, save_incident_to_db
from src.integrations.github import create_fix_pull_request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("opspulse")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("OpsPulse AI ready (model=%s)", settings.groq_model)
    yield
    flush_langfuse()


app = FastAPI(title="OpsPulse AI", version="1.0.0", lifespan=lifespan)


class IncidentWebhook(BaseModel):
    error_message: str = Field(..., min_length=1, max_length=20_000)
    stack_trace: str = Field("", max_length=100_000)
    repo_name: str = Field(..., pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", description="GitHub 'owner/repo'")


class WebhookAccepted(BaseModel):
    incident_id: str
    status: str


def _check_secret(provided: Optional[str]) -> None:
    if settings.webhook_secret and not hmac.compare_digest(provided or "", settings.webhook_secret):
        raise HTTPException(status_code=401, detail="invalid webhook secret")


def build_pull_request_body(state: IncidentState, incident_id: uuid.UUID) -> str:
    rca = state.get("root_cause_analysis") or {}
    summary = rca.get("incident_summary", {})
    root = rca.get("diagnostic_chain", {}).get("primary_root_cause", {})
    remediation = rca.get("patch_remediation", {})
    flow = rca.get("control_flow", {})
    checks = flow.get("checks", {})
    rows = "\n".join(f"| {name} | {c['score']:.2f} / {c['max']:.2f} |" for name, c in checks.items())
    return (
        f"## 🤖 OpsPulse AI automated fix\n\n"
        f"**Incident:** {summary.get('title', 'n/a')}  \n"
        f"**Severity:** {summary.get('severity', 'n/a')}  \n"
        f"**Trigger frame:** `{summary.get('trigger_frame', 'n/a')}`  \n"
        f"**Confidence (deterministic gate):** {state['confidence_score']:.2f} after {state['iterations']} iteration(s)  \n"
        f"**Incident ID:** `{incident_id}`\n\n"
        f"### Root cause\n{root.get('technical_explanation', 'n/a')}\n\n"
        f"**Symptom vs cause:** {root.get('symptom_vs_cause', 'n/a')}\n\n"
        f"### Fix\n{remediation.get('explanation', 'n/a')}\n\n"
        f"**Side effects:** {remediation.get('side_effects', 'n/a')}\n\n"
        f"### Quality gate\n| Check | Score |\n|---|---|\n{rows}\n\n"
        f"> ⚠️ Generated automatically. Review the change and run your test suite before merging."
    )


def run_incident_pipeline(incident_id: uuid.UUID, payload: IncidentWebhook) -> Dict[str, Any]:
    """Full flow: graph -> save to Neon -> (high confidence) open a GitHub PR -> update Neon."""
    state = initial_state(payload.error_message, payload.stack_trace, payload.repo_name)
    fingerprint = compute_fingerprint(payload.repo_name, payload.error_message, payload.stack_trace)
    config = build_run_config(str(incident_id), payload.repo_name, fingerprint)

    try:
        final: IncidentState = ops_pulse_graph.invoke(state, config=config)
    except Exception as exc:
        logger.exception("graph failed for incident %s", incident_id)
        try:
            save_incident_to_db(state, incident_id=incident_id, status="failed", failure_reason=f"{type(exc).__name__}: {exc}"[:2000])
        except SQLAlchemyError:
            logger.exception("could not persist failure for %s", incident_id)
        flush_langfuse()
        return {"incident_id": str(incident_id), "status": "failed", "error": str(exc)}

    status, pr, failure = "needs_review", {}, None
    save_incident_to_db(final, incident_id=incident_id, status="analysis_complete")  # persist analysis first

    if final["confidence_score"] >= settings.confidence_threshold and final.get("suggested_patch") and final.get("affected_file"):
        existing = find_recent_pr(payload.repo_name, fingerprint)
        if existing:
            status, pr = "pr_skipped_duplicate", {"pr_url": existing}
        else:
            try:
                created = create_fix_pull_request(
                    repo_name=payload.repo_name,
                    file_path=final["affected_file"],
                    unified_diff=final["suggested_patch"],
                    title=f"[OpsPulse] {(final['root_cause_analysis'] or {}).get('incident_summary', {}).get('title', 'Automated incident fix')}",
                    body=build_pull_request_body(final, incident_id),
                    fingerprint=fingerprint,
                )
                status, pr = "pr_created", created
            except Exception as exc:
                logger.exception("PR creation failed for %s", incident_id)
                status, failure = "pr_failed", f"{type(exc).__name__}: {exc}"[:2000]

    save_incident_to_db(
        final,
        incident_id=incident_id,
        status=status,
        pr_url=pr.get("pr_url"),
        pr_number=pr.get("pr_number"),
        pr_branch=pr.get("branch"),
        failure_reason=failure,
    )
    flush_langfuse()
    logger.info("incident %s finished: status=%s confidence=%.2f", incident_id, status, final["confidence_score"])
    return {
        "incident_id": str(incident_id),
        "status": status,
        "confidence_score": final["confidence_score"],
        "iterations": final["iterations"],
        "affected_file": final.get("affected_file"),
        "pr_url": pr.get("pr_url"),
        "root_cause_analysis": final.get("root_cause_analysis"),
        "suggested_patch": final.get("suggested_patch"),
    }


@app.get("/healthz")
def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/incident", status_code=202)
def webhook_incident(
    payload: IncidentWebhook,
    background_tasks: BackgroundTasks,
    wait: bool = Query(False, description="Run synchronously and return the full result"),
    x_webhook_secret: Optional[str] = Header(None),
):
    _check_secret(x_webhook_secret)
    incident_id = uuid.uuid4()
    state = initial_state(payload.error_message, payload.stack_trace, payload.repo_name)
    try:
        save_incident_to_db(state, incident_id=incident_id, status="processing")
    except SQLAlchemyError as exc:
        logger.exception("database unavailable")
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    if wait:
        return JSONResponse(status_code=200, content=jsonable_encoder(run_incident_pipeline(incident_id, payload)))
    background_tasks.add_task(run_incident_pipeline, incident_id, payload)
    return WebhookAccepted(incident_id=str(incident_id), status="processing")


@app.get("/incidents/{incident_id}")
def read_incident(incident_id: uuid.UUID, x_webhook_secret: Optional[str] = Header(None)):
    _check_secret(x_webhook_secret)
    row = get_incident(incident_id)
    if row is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return row
