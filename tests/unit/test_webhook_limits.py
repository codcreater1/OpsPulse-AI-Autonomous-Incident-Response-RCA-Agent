"""Webhook limits that only show with many alerts or a body that does not announce its size."""

import copy
import json

from src.integrations.alertmanager import MAX_ALERTS
from tests.unit.test_alertmanager import BEARER, NOTIFICATION


def _many(count):
    notification = copy.deepcopy(NOTIFICATION)
    first = notification["alerts"][0]
    notification["alerts"] = [
        {**copy.deepcopy(first), "fingerprint": f"fp{i:04d}", "labels": {**first["labels"], "alertname": f"A{i}"}}
        for i in range(count)
    ]
    return notification


def test_alerts_beyond_the_limit_are_dropped_and_counted_not_silently_lost(client, caplog):
    resp = client.post("/integrations/alertmanager", json=_many(MAX_ALERTS + 3), headers=BEARER)
    body = resp.json()
    assert resp.status_code == 202 and len(body["alerts"]) == MAX_ALERTS and body["dropped"] == 3
    assert "3 firing alerts beyond the limit were dropped" in caplog.text


def test_exactly_the_limit_drops_nothing(client):
    body = client.post("/integrations/alertmanager", json=_many(MAX_ALERTS), headers=BEARER).json()
    assert len(body["alerts"]) == MAX_ALERTS and body["dropped"] == 0


def test_a_streamed_body_over_the_limit_is_refused_without_a_content_length(client):
    def chunks():
        for _ in range(200):
            yield b"x" * 10_000  # 2 MB in total, announced nowhere

    resp = client.post("/integrations/alertmanager", content=chunks(), headers=BEARER)
    assert resp.status_code == 413
    assert json.loads(resp.text)["error"]["code"] == "payload_too_large"
