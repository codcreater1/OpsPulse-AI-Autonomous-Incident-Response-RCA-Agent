"""Incident listing (filters, keyset pagination) and the Prometheus endpoint."""

import uuid

from src.db import repositories
from tests.unit.conftest import API_HEADERS, REPORTER_HEADERS
from tests.unit.factories import BAD_DIFF, incident_payload, make_analysis


def _seed(n, status="analysis_ready", repo="o/r"):
    ids = []
    for _ in range(n):
        incident_id = uuid.uuid4()
        repositories.create_incident(incident_id, repo, "f" * 64, "TypeError", "", "alice")
        repositories.update_incident(incident_id, status=status)
        ids.append(str(incident_id))
    return ids


def test_pagination_walks_every_incident_exactly_once(client):
    seeded = set(_seed(7))
    seen, cursor = [], None
    for _ in range(10):
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        page = client.get("/incidents", params=params, headers=REPORTER_HEADERS).json()
        seen += [item["incident_id"] for item in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == 7 and set(seen) == seeded


def test_filters_by_status_and_repository(client):
    waiting = set(_seed(2, status="awaiting_approval"))
    _seed(3)
    _seed(1, status="awaiting_approval", repo="o/other")
    page = client.get(
        "/incidents", params={"status": "awaiting_approval", "repo_name": "O/R"}, headers=API_HEADERS
    ).json()
    assert {i["incident_id"] for i in page["items"]} == waiting and page["next_cursor"] is None


def test_invalid_listing_parameters(client):
    assert client.get("/incidents", params={"cursor": "not-a-cursor"}, headers=API_HEADERS).status_code == 400
    assert client.get("/incidents", params={"status": "bogus"}, headers=API_HEADERS).status_code == 422
    assert client.get("/incidents", params={"limit": 1000}, headers=API_HEADERS).status_code == 422
    assert client.get("/incidents").status_code == 401


def test_metrics_reflect_pipeline_outcomes_without_content(client, fake_llm, source_fetch):
    fake_llm([make_analysis(BAD_DIFF), make_analysis()])
    client.post("/webhook/incident?wait=true", json=incident_payload(), headers=API_HEADERS)
    text = client.get("/metrics").text
    assert 'opspulse_llm_attempts_total{outcome="valid"}' in text
    assert 'opspulse_quality_gate_evaluations_total{result="rejected"}' in text
    assert 'opspulse_incidents_finished_total{error_category="remediation_skipped",status="analysis_ready"}' in text
    assert "o/r" not in text and "TypeError" not in text and "src/app.py" not in text


def test_metrics_can_be_disabled(client, set_settings):
    set_settings(metrics_enabled=False)
    assert client.get("/metrics").status_code == 404
