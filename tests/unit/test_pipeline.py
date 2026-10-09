"""End-to-end through the HTTP API with fake LLM / fake GitHub and a real (SQLite) database."""

import uuid

import pytest
from sqlalchemy.exc import OperationalError

from src.db import repositories
from src.integrations.github import GitHubError, PullRequestResult
from src.services import remediation_service
from tests.unit.conftest import API_HEADERS
from tests.unit.factories import BAD_DIFF, incident_payload, make_analysis


@pytest.fixture
def github_pr(monkeypatch, set_settings):
    """Enable remediation and capture PR creation calls instead of calling GitHub."""
    set_settings(enable_github_remediation=True, github_token="test-token", require_remediation_approval=False)
    created = []

    def fake_create(**kwargs):
        created.append(kwargs)
        return PullRequestResult("https://github.com/o/r/pull/7", 7, "opspulse/fix-abc", already_existed=False)

    monkeypatch.setattr(remediation_service, "create_fix_pull_request", fake_create)
    return created


def submit(client, wait=True, **overrides):
    url = "/webhook/incident?wait=true" if wait else "/webhook/incident"
    return client.post(url, json=incident_payload(**overrides), headers=API_HEADERS)


def test_analysis_only_mode_without_github_credentials(client, fake_llm, source_fetch):
    fake_llm([make_analysis()])
    body = submit(client).json()
    assert body["status"] == "analysis_ready"
    assert "ENABLE_GITHUB_REMEDIATION=false" in body["status_reason"]
    assert body["error_category"] == "remediation_skipped"
    assert body["analysis"]["evaluation"]["quality_gate_passed"] is True and body["pr_url"] is None


def test_missing_token_is_explained(client, fake_llm, source_fetch, set_settings):
    set_settings(enable_github_remediation=True, github_token="")
    fake_llm([make_analysis()])
    assert "GITHUB_TOKEN not configured" in submit(client).json()["status_reason"]


def test_self_correction_then_pr_and_persistence(client, fake_llm, source_fetch, github_pr):
    llm = fake_llm([make_analysis(BAD_DIFF), make_analysis()])
    body = submit(client).json()
    assert body["status"] == "pr_created" and body["iterations"] == 2 and body["quality_score"] >= 0.85
    assert body["pr_number"] == 7 and llm.calls == 2
    assert len(github_pr) == 1 and github_pr[0]["file_path"] == "src/app.py"
    assert "No tests were executed" in github_pr[0]["body"]
    stored = repositories.get_incident(uuid.UUID(body["incident_id"]))
    assert stored["status"] == "pr_created" and stored["analysis"]["execution_metadata"]["iteration"] == 2


def test_rejected_analysis_never_reaches_github(client, fake_llm, source_fetch, github_pr):
    fake_llm([make_analysis(BAD_DIFF)] * 3)
    body = submit(client).json()
    assert body["status"] == "needs_review" and body["iterations"] == 3 and not github_pr
    assert body["status_reason"] == "analysis attempt budget exhausted"
    assert body["error_category"] == "retry_budget_exhausted"
    assert [a["iteration"] for a in body["analysis"]["attempts"]] == [1, 2, 3]


def test_duplicate_failure_does_not_open_a_second_pr(client, fake_llm, source_fetch, github_pr):
    llm = fake_llm([make_analysis(), make_analysis()])
    assert submit(client).json()["status"] == "pr_created"
    second = submit(client).json()
    assert second["status"] == "pr_skipped_duplicate" and second["pr_url"].endswith("/pull/7")
    assert len(github_pr) == 1
    assert "same failure fingerprint" in llm.prompts[1]  # history lookup surfaced the earlier incident


def test_github_failure_is_reported_as_pr_failed(client, fake_llm, source_fetch, github_pr, monkeypatch):
    def failing(**_):
        raise GitHubError("GitHub token lacks permission (or secondary rate limit)")

    monkeypatch.setattr(remediation_service, "create_fix_pull_request", failing)
    fake_llm([make_analysis()])
    body = submit(client).json()
    assert body["status"] == "pr_failed" and "lacks permission" in body["status_reason"]
    assert body["error_category"] == "github_unavailable"


def test_database_failure_after_analysis_returns_503_and_opens_no_pr(
    client, fake_llm, source_fetch, github_pr, monkeypatch
):
    fake_llm([make_analysis()])

    def broken_update(*_, **__):
        raise OperationalError("UPDATE", {}, Exception("connection lost"))

    monkeypatch.setattr(repositories, "update_incident", broken_update)
    resp = submit(client)
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "service_unavailable"
    assert not github_pr


def test_llm_outage_is_persisted_as_failed(client, source_fetch):
    body = submit(client).json()  # GROQ_API_KEY is empty in the unit-test environment
    assert body["status"] == "failed" and body["error_category"] == "llm_not_configured"
    assert body["status_reason"] == "GROQ_API_KEY is not set"


def test_async_submission_then_poll(client, fake_llm, source_fetch):
    fake_llm([make_analysis()])
    resp = submit(client, wait=False)
    assert resp.status_code == 202 and resp.json()["status"] == "processing"
    # TestClient runs background tasks before returning, so the result is already stored.
    polled = client.get(f"/incidents/{resp.json()['incident_id']}", headers=API_HEADERS).json()
    assert polled["status"] == "analysis_ready"
