"""NUL (U+0000) in input: SQLite stores it, PostgreSQL rejects it, so it is removed before anything is persisted."""

import uuid

from src.db import repositories
from tests.unit.conftest import API_HEADERS
from tests.unit.test_alertmanager import BEARER, NOTIFICATION
from tests.unit.test_sentry import EVENT_ALERT
from tests.unit.test_sentry import _post as sentry_post

RAW = b'{"repo_name":"o/r","error_message":"Type\\u0000Error: x","stack_trace":"line\\u0000 1"}'


def test_nul_bytes_in_a_reported_error_are_not_stored(client):
    resp = client.post("/webhook/incident", content=RAW, headers={**API_HEADERS, "Content-Type": "application/json"})
    assert resp.status_code == 202
    row = repositories.get_incident(uuid.UUID(resp.json()["incident_id"]))
    assert row["error_message"] == "TypeError: x" and "\x00" not in str(row)


def test_the_same_error_with_and_without_nul_is_one_failure():
    from src.agent.parsing import compute_fingerprint
    from src.services.incident_service import _without_nul

    a, b = "Type\x00Error: x", "TypeError: x"
    assert compute_fingerprint("o/r", _without_nul(a), "") == compute_fingerprint("o/r", b, "")


def test_nul_in_a_sentry_event_is_removed_too(client):
    event = EVENT_ALERT.copy()
    event["data"] = {**EVENT_ALERT["data"], "event": {**EVENT_ALERT["data"]["event"], "title": "Bad\x00Thing"}}
    resp = sentry_post(client, event)
    assert resp.status_code == 202
    row = repositories.get_incident(uuid.UUID(resp.json()["incident_id"]))
    assert "\x00" not in row["error_message"]


def test_nul_in_an_alertmanager_alert_is_removed_too(client):
    notification = {**NOTIFICATION, "alerts": [dict(NOTIFICATION["alerts"][0])]}
    notification["alerts"][0]["annotations"] = {**notification["alerts"][0]["annotations"], "summary": "Disk\x00 full"}
    resp = client.post("/integrations/alertmanager", json=notification, headers=BEARER)
    assert resp.status_code == 202
    rows, _ = repositories.list_incidents(None, None, 10, None)
    stored = repositories.get_incident(uuid.UUID(rows[0]["incident_id"]))
    assert "\x00" not in stored["error_message"]
