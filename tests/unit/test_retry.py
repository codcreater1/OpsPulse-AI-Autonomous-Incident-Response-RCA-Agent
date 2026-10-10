"""Transient provider errors are retried with backoff through the queue; failed incidents can be re-queued."""

import uuid
from datetime import UTC, datetime, timedelta

import groq
import httpx
from sqlalchemy import update

from src.db import repositories
from src.db.client import session_scope
from src.db.models import Incident
from src.worker import Worker
from tests.unit.conftest import API_HEADERS, REPORTER_HEADERS, REVIEWER_HEADERS
from tests.unit.factories import incident_payload, make_analysis


def _rate_limited(monkeypatch):
    class Limited:
        def invoke(self, messages, config=None):
            request = httpx.Request("POST", "https://api.groq.test")
            raise groq.RateLimitError("slow down", response=httpx.Response(429, request=request), body=None)

    monkeypatch.setattr("src.integrations.llm.get_chat_model", lambda temperature: Limited())


def _make_available(incident_id):
    with session_scope() as session:
        session.execute(
            update(Incident).where(Incident.id == incident_id).values(available_at=datetime.now(UTC) - timedelta(1))
        )


def _submit(client):
    resp = client.post("/webhook/incident", json=incident_payload(), headers=API_HEADERS)
    return uuid.UUID(resp.json()["incident_id"])


def test_rate_limit_defers_the_incident_with_backoff(client, source_fetch, monkeypatch):
    _rate_limited(monkeypatch)
    incident_id = _submit(client)
    assert Worker().run_once()
    row = repositories.get_incident(incident_id)
    assert row["status"] == "queued" and row["error_category"] == "llm_rate_limited"
    assert "retrying in 60s" in row["status_reason"]
    assert datetime.fromisoformat(row["available_at"]) > datetime.now(UTC)
    assert Worker().run_once() is False  # not claimable during the backoff


def test_backoff_grows_and_the_retry_budget_is_bounded(client, source_fetch, monkeypatch, set_settings):
    set_settings(max_transient_retries=3, max_job_attempts=5)
    _rate_limited(monkeypatch)
    incident_id = _submit(client)
    reasons = []
    for _ in range(3):
        assert Worker().run_once()
        row = repositories.get_incident(incident_id)
        reasons.append(row["status_reason"])
        _make_available(incident_id)
    assert "retrying in 60s" in reasons[0] and "retrying in 120s" in reasons[1]
    assert row["status"] == "failed" and row["error_category"] == "llm_rate_limited" and row["job_attempts"] == 3


def test_a_deferred_incident_succeeds_once_the_provider_recovers(client, source_fetch, monkeypatch, fake_llm):
    _rate_limited(monkeypatch)
    incident_id = _submit(client)
    Worker().run_once()
    _make_available(incident_id)
    fake_llm([make_analysis()])
    assert Worker().run_once()
    assert repositories.get_incident(incident_id)["status"] == "analysis_ready"


def test_permanent_errors_are_not_retried(client, source_fetch):
    incident_id = _submit(client)  # no GROQ_API_KEY in tests: llm_not_configured is permanent
    Worker().run_once()
    row = repositories.get_incident(incident_id)
    assert row["status"] == "failed" and row["error_category"] == "llm_not_configured"


def test_manual_retry_requeues_a_failed_incident(client, source_fetch, fake_llm):
    incident_id = _submit(client)
    Worker().run_once()  # fails: llm_not_configured
    url = f"/incidents/{incident_id}/retry"
    assert client.post(url, headers=REPORTER_HEADERS).status_code == 403
    resp = client.post(url, headers=REVIEWER_HEADERS)
    assert resp.status_code == 200 and resp.json()["status"] == "queued" and resp.json()["job_attempts"] == 0
    assert "re-queued by bob" in resp.json()["status_reason"]
    assert client.post(url, headers=REVIEWER_HEADERS).status_code == 409  # no longer failed
    fake_llm([make_analysis()])
    assert Worker().run_once()
    assert repositories.get_incident(incident_id)["status"] == "analysis_ready"


def test_retry_of_unknown_incident_is_404(client):
    assert client.post(f"/incidents/{uuid.uuid4()}/retry", headers=REVIEWER_HEADERS).status_code == 404
