"""Sentry webhook adapter: signature verification, payload translation, mapping, idempotency, limits."""

import copy
import hashlib
import hmac
import json

import pytest

from src.integrations.sentry import parse_project_map, signature_is_valid, to_incident
from src.worker import Worker
from tests.unit.conftest import API_HEADERS
from tests.unit.factories import make_analysis

SECRET = "sentry-test-secret"

# Shape follows the documented issue-alert payload (data.event.exception.values[].stacktrace.frames[]).
EVENT_ALERT = {
    "action": "triggered",
    "actor": {"id": "sentry", "name": "Sentry", "type": "application"},
    "installation": {"uuid": "7a485448-a9e2-4c85-8a3c-4f44175783c9"},
    "data": {
        "triggered_rule": "Every error",
        "event": {
            "event_id": "c1f3a2b4d5e6f708192a3b4c5d6e7f80",
            "project": 1,
            "title": "TypeError: 'NoneType' object is not subscriptable",
            "exception": {
                "values": [
                    {
                        "type": "TypeError",
                        "value": "'NoneType' object is not subscriptable",
                        "stacktrace": {
                            "frames": [
                                {
                                    "abs_path": "/usr/lib/python3.11/site-packages/flask/app.py",
                                    "lineno": 880,
                                    "function": "full_dispatch_request",
                                    "in_app": False,
                                },
                                {
                                    "abs_path": "/app/src/app.py",
                                    "lineno": 14,
                                    "function": "main",
                                    "in_app": True,
                                    "context_line": "    print(load_user({}))",
                                },
                                {
                                    "abs_path": "/app/src/app.py",
                                    "lineno": 6,
                                    "function": "load_user",
                                    "in_app": True,
                                    "context_line": '    name = profile["name"]',
                                },
                            ]
                        },
                    }
                ]
            },
        },
    },
}


def _post(client, payload, resource="event_alert", secret=SECRET, compact=False, signature=None):
    body = json.dumps(payload, separators=(",", ":") if compact else (", ", ": ")).encode()
    signed = json.dumps(payload, separators=(",", ":")).encode() if compact else body
    sig = signature if signature is not None else hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "Sentry-Hook-Resource": resource, "Sentry-Hook-Signature": sig}
    return client.post("/integrations/sentry", content=body, headers=headers)


def test_translation_keeps_application_frames_in_traceback_order():
    incident = to_incident(EVENT_ALERT)
    assert incident.project_id == "1"
    assert incident.error_message == "TypeError: 'NoneType' object is not subscriptable"
    lines = incident.stack_trace.splitlines()
    assert lines[0] == "Traceback (most recent call last):" and "site-packages" not in incident.stack_trace
    assert lines[-3:] == [
        '  File "/app/src/app.py", line 6, in load_user',
        '    name = profile["name"]',
        incident.error_message,
    ]
    assert to_incident(copy.deepcopy(EVENT_ALERT)).incident_id == incident.incident_id  # stable per event


def test_signature_accepts_raw_and_compact_json_forms_only_with_the_right_secret():
    body = json.dumps(EVENT_ALERT, indent=2).encode()
    raw_sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    compact_sig = hmac.new(
        SECRET.encode(), json.dumps(EVENT_ALERT, separators=(",", ":")).encode(), hashlib.sha256
    ).hexdigest()
    assert signature_is_valid(SECRET, body, raw_sig) and signature_is_valid(SECRET, body, compact_sig)
    assert not signature_is_valid("other-secret", body, raw_sig)
    assert not signature_is_valid(SECRET, body, None) and not signature_is_valid("", body, raw_sig)


def test_project_map_parsing():
    assert parse_project_map("1:Org/Repo, 42:o/r") == {"1": "org/repo", "42": "o/r"}
    with pytest.raises(ValueError):
        parse_project_map("1-org-repo")


def test_signed_event_becomes_a_queued_incident_and_is_analysed(client, fake_llm, source_fetch):
    resp = _post(client, EVENT_ALERT)
    assert resp.status_code == 202 and resp.json()["status"] == "queued"
    incident_id = resp.json()["incident_id"]
    fake_llm([make_analysis()])
    assert Worker().run_once()
    body = client.get(f"/incidents/{incident_id}", headers=API_HEADERS).json()
    assert body["repo_name"] == "o/r" and body["submitted_by"] == "sentry"
    assert body["affected_file"] == "src/app.py" and body["status"] == "analysis_ready"


def test_compact_signature_variant_is_accepted(client):
    assert _post(client, EVENT_ALERT, compact=True).status_code == 202


def test_redelivery_is_idempotent(client):
    first = _post(client, EVENT_ALERT)
    again = _post(client, EVENT_ALERT)
    assert again.status_code == 200 and again.json()["incident_id"] == first.json()["incident_id"]


@pytest.mark.parametrize("signature", ["", "0" * 64, "not-hex"])
def test_bad_signatures_are_rejected(client, signature):
    assert _post(client, EVENT_ALERT, signature=signature).status_code == 401


def test_wrong_secret_is_rejected(client):
    assert _post(client, EVENT_ALERT, secret="guess").status_code == 401


def test_other_resources_are_ignored(client):
    assert _post(client, {"action": "created", "data": {}}, resource="installation").status_code == 204


def test_unmapped_and_unallowed_projects_are_refused(client):
    unmapped = copy.deepcopy(EVENT_ALERT)
    unmapped["data"]["event"]["project"] = 99
    assert _post(client, unmapped).status_code == 422
    other = copy.deepcopy(EVENT_ALERT)
    other["data"]["event"]["project"] = 2  # mapped to a repository that is not allow-listed
    assert _post(client, other).status_code == 403


def test_payload_without_an_event_is_unprocessable(client):
    assert _post(client, {"data": {}}).status_code == 422


def test_oversized_payload_is_rejected(client):
    huge = copy.deepcopy(EVENT_ALERT)
    huge["data"]["event"]["title"] = "x" * 1_100_000
    assert _post(client, huge).status_code == 413


def test_disabled_without_a_client_secret(client, set_settings):
    set_settings(sentry_client_secret="")
    assert _post(client, EVENT_ALERT).status_code == 404
