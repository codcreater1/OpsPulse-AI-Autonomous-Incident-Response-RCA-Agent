"""Alertmanager webhook: payload translation, Bearer authentication, repository mapping and idempotency."""

import copy

import pytest

from src.integrations.alertmanager import MAX_ALERTS, AlertmanagerPayloadError, to_incidents
from src.worker import Worker
from tests.unit.conftest import API_HEADERS
from tests.unit.factories import TRACE, make_analysis

BEARER = {"Authorization": "Bearer reporter-key"}  # alice, reporter role

# Shape follows the documented webhook payload (version 4).
NOTIFICATION = {
    "version": "4",
    "groupKey": '{}:{alertname="CheckoutErrors"}',
    "truncatedAlerts": 0,
    "status": "firing",
    "receiver": "opspulse",
    "groupLabels": {"alertname": "CheckoutErrors"},
    "commonLabels": {"alertname": "CheckoutErrors"},
    "commonAnnotations": {},
    "externalURL": "http://alertmanager:9093",
    "alerts": [
        {
            "status": "firing",
            "labels": {"alertname": "CheckoutErrors", "repository": "O/R", "severity": "page"},
            "annotations": {
                "summary": "5xx rate above 5% on /checkout",
                "description": "TypeError: 'NoneType' object is not subscriptable",
                "stack_trace": TRACE,
            },
            "startsAt": "2026-10-10T12:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "http://prometheus:9090/graph",
            "fingerprint": "a1b2c3d4e5f60718",
        },
        {
            "status": "resolved",
            "labels": {"alertname": "Old", "repository": "o/r"},
            "annotations": {},
            "startsAt": "2026-10-10T10:00:00Z",
            "endsAt": "2026-10-10T11:00:00Z",
            "fingerprint": "ffff",
        },
    ],
}


def _post(client, payload, headers=BEARER):
    return client.post("/integrations/alertmanager", json=payload, headers=headers)


def test_translation_keeps_firing_alerts_only():
    incidents, dropped = to_incidents(NOTIFICATION, "repository")
    assert dropped == 0 and len(incidents) == 1
    alert = incidents[0]
    assert alert.repo_name == "o/r" and alert.alert_name == "CheckoutErrors"
    assert alert.error_message.startswith("CheckoutErrors: 5xx rate above 5% on /checkout\nTypeError")
    assert alert.stack_trace == TRACE.strip()
    assert to_incidents(copy.deepcopy(NOTIFICATION), "repository")[0][0].incident_id == alert.incident_id


@pytest.mark.parametrize("payload", [{}, {"version": "3", "alerts": []}, {"version": "4", "alerts": "x"}])
def test_non_alertmanager_payloads_are_refused(payload):
    with pytest.raises(AlertmanagerPayloadError):
        to_incidents(payload, "repository")


def test_large_groups_are_truncated_and_reported():
    payload = copy.deepcopy(NOTIFICATION)
    alert = payload["alerts"][0]
    payload["alerts"] = [{**alert, "fingerprint": f"f{i}"} for i in range(MAX_ALERTS + 3)]
    incidents, dropped = to_incidents(payload, "repository")
    assert len(incidents) == MAX_ALERTS and dropped == 3


def test_firing_alert_becomes_an_analysed_incident(client, fake_llm, source_fetch):
    resp = _post(client, NOTIFICATION)
    assert resp.status_code == 202
    (outcome,) = resp.json()["alerts"]
    assert outcome["outcome"] == "queued"
    fake_llm([make_analysis()])
    assert Worker().run_once()
    body = client.get(f"/incidents/{outcome['incident_id']}", headers=API_HEADERS).json()
    assert body["submitted_by"] == "alice" and body["repo_name"] == "o/r" and body["status"] == "analysis_ready"


def test_repeated_notification_is_idempotent(client):
    first = _post(client, NOTIFICATION).json()["alerts"][0]
    again = _post(client, NOTIFICATION).json()["alerts"][0]
    assert again == {**first, "outcome": "duplicate"}


def test_missing_or_unallowed_repository_is_skipped_not_failed(client):
    payload = copy.deepcopy(NOTIFICATION)
    payload["alerts"][0]["labels"]["repository"] = "other/repo"
    payload["alerts"].append({**payload["alerts"][0], "labels": {"alertname": "NoRepo"}, "fingerprint": "n"})
    outcomes = _post(client, payload).json()["alerts"]
    assert [(o["outcome"], o["detail"]) for o in outcomes] == [
        ("skipped", "repository not allowed"),
        ("skipped", "label 'repository' missing or not 'owner/repo'"),
    ]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic cmVwb3J0ZXI="}])
def test_requires_a_valid_key(client, headers):
    assert _post(client, NOTIFICATION, headers).status_code == 401


def test_bearer_token_works_on_the_regular_api(client):
    assert client.get("/incidents", headers=BEARER).status_code == 200
