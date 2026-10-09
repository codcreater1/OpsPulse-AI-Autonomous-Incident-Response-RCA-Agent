"""HTTP contract: validation, authentication, authorization, error format, idempotency, health."""

import uuid

from sqlalchemy.exc import OperationalError

from src.db import repositories
from tests.unit.conftest import API_HEADERS
from tests.unit.factories import incident_payload, make_analysis


def _db_down(*_, **__):
    raise OperationalError("SELECT 1", {}, Exception("could not connect to postgres://user:secret@db/x"))


def test_healthz_is_public_and_minimal(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200 and resp.json() == {"status": "ok", "checks": {}}


def test_readyz_reports_database_without_details(client, monkeypatch):
    assert client.get("/readyz").json() == {"status": "ready", "checks": {"database": "ok"}}
    monkeypatch.setattr("src.api.routes.ping_database", _db_down)
    resp = client.get("/readyz")
    assert resp.status_code == 503 and "secret" not in resp.text and "postgres" not in resp.text


def test_missing_or_wrong_api_key_is_rejected(client):
    assert client.post("/webhook/incident", json=incident_payload()).status_code == 401
    resp = client.post("/webhook/incident", json=incident_payload(), headers={"X-API-Key": "nope"})
    assert resp.status_code == 401 and resp.json()["error"]["code"] == "unauthorized"
    assert client.get(f"/incidents/{uuid.uuid4()}").status_code == 401


def test_api_fails_closed_when_no_key_is_configured(client, set_settings):
    set_settings(api_key="")
    resp = client.post("/webhook/incident", json=incident_payload())
    assert resp.status_code == 503 and "API_KEY" in resp.json()["error"]["message"]


def test_explicit_dev_opt_out_allows_unauthenticated(client, set_settings, fake_llm, source_fetch):
    set_settings(api_key="", allow_unauthenticated=True)
    fake_llm([make_analysis()])
    assert client.post("/webhook/incident", json=incident_payload()).status_code == 202


def test_validation_errors_do_not_echo_input(client):
    secret_looking = "x" * 20_001
    resp = client.post("/webhook/incident", json=incident_payload(error_message=secret_looking), headers=API_HEADERS)
    body = resp.json()
    assert resp.status_code == 422 and body["error"]["code"] == "validation_error"
    assert "xxxxxxxxxx" not in resp.text and "error_message" in body["error"]["message"]


def test_invalid_payloads(client):
    cases = [
        incident_payload(repo_name="not a repo"),
        incident_payload(repo_name="../../etc/passwd"),
        incident_payload(repo_name="../etc"),
        incident_payload(error_message=""),
        incident_payload(stack_trace="y" * 100_001),
        incident_payload(unexpected_field="x"),
        incident_payload(incident_id="not-a-uuid"),
    ]
    for payload in cases:
        assert client.post("/webhook/incident", json=payload, headers=API_HEADERS).status_code == 422, payload


def test_repository_must_be_allow_listed(client):
    resp = client.post("/webhook/incident", json=incident_payload(repo_name="someone/else"), headers=API_HEADERS)
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "forbidden"


def test_repo_name_is_case_insensitive(client, fake_llm, source_fetch):
    fake_llm([make_analysis()])
    resp = client.post("/webhook/incident", json=incident_payload(repo_name="O/R"), headers=API_HEADERS)
    assert resp.status_code == 202


def test_database_outage_on_submit_returns_503_not_success(client, monkeypatch):
    monkeypatch.setattr(repositories, "create_incident", _db_down)
    resp = client.post("/webhook/incident", json=incident_payload(), headers=API_HEADERS)
    assert resp.status_code == 503 and "secret" not in resp.text


def test_unknown_incident_is_404(client):
    resp = client.get(f"/incidents/{uuid.uuid4()}", headers=API_HEADERS)
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "not_found"


def test_repeated_delivery_with_same_incident_id_is_idempotent(client, fake_llm, source_fetch):
    llm = fake_llm([make_analysis()])
    incident_id = str(uuid.uuid4())
    first = client.post(
        "/webhook/incident?wait=true", json=incident_payload(incident_id=incident_id), headers=API_HEADERS
    )
    again = client.post(
        "/webhook/incident?wait=true", json=incident_payload(incident_id=incident_id), headers=API_HEADERS
    )
    assert first.status_code == 200 and again.status_code == 200
    assert again.json()["incident_id"] == incident_id and again.json()["status"] == first.json()["status"]
    assert llm.calls == 1  # the second delivery did not trigger a new analysis


def test_incident_id_reused_for_another_repo_conflicts(client, fake_llm, source_fetch, set_settings):
    set_settings(allowed_repositories=frozenset({"o/r", "o/other"}))
    fake_llm([make_analysis()])
    incident_id = str(uuid.uuid4())
    client.post("/webhook/incident", json=incident_payload(incident_id=incident_id), headers=API_HEADERS)
    resp = client.post(
        "/webhook/incident", json=incident_payload(incident_id=incident_id, repo_name="o/other"), headers=API_HEADERS
    )
    assert resp.status_code == 409


def test_openapi_documents_the_api_key_scheme(client):
    schema = client.get("/openapi.json").json()
    assert "APIKeyHeader" in schema["components"]["securitySchemes"]
    assert "/webhook/incident" in schema["paths"] and "/incidents/{incident_id}" in schema["paths"]
