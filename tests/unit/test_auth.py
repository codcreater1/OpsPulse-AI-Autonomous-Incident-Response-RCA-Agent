"""Identity configuration, role checks, rate limiting and recovery of interrupted incidents."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from src.api.auth import SlidingWindowLimiter
from src.config import ConfigError, _identities
from src.db import repositories
from src.db.client import session_scope
from src.db.models import Incident
from src.services import incident_service
from tests.unit.conftest import REPORTER_HEADERS
from tests.unit.factories import incident_payload, make_analysis

HASH = hashlib.sha256(b"k").hexdigest()


@pytest.mark.parametrize(
    "value",
    [
        "alice:reviewer",
        f"alice:root:{HASH}",
        "alice:reviewer:notahash",
        f":reviewer:{HASH}",
        f"a:reviewer:{HASH},a:admin:{HASH}",
    ],
)
def test_invalid_api_keys_configuration_is_rejected(monkeypatch, value):
    monkeypatch.setenv("API_KEYS", value)
    monkeypatch.delenv("API_KEY", raising=False)
    with pytest.raises(ConfigError):
        _identities()


def test_configuration_stores_digests_not_keys(monkeypatch):
    monkeypatch.setenv("API_KEYS", f"ci:reporter:{HASH}")
    monkeypatch.setenv("API_KEY", "legacy-secret")
    ids = _identities()
    assert [(i.name, i.role) for i in ids] == [("ci", "reporter"), ("default", "admin")]
    assert all("legacy-secret" not in repr(i) for i in ids)


def test_reporter_can_submit_and_read(client, fake_llm, source_fetch):
    fake_llm([make_analysis()])
    resp = client.post("/webhook/incident", json=incident_payload(), headers=REPORTER_HEADERS)
    assert resp.status_code == 202
    body = client.get(f"/incidents/{resp.json()['incident_id']}", headers=REPORTER_HEADERS).json()
    assert body["submitted_by"] == "alice"


def test_rate_limit_returns_429_with_retry_after(client, fake_llm, source_fetch, set_settings):
    set_settings(rate_limit_per_minute=2)
    fake_llm([make_analysis()] * 3)
    responses = [client.post("/webhook/incident", json=incident_payload(), headers=REPORTER_HEADERS) for _ in range(3)]
    assert [r.status_code for r in responses] == [202, 202, 429]
    assert responses[2].json()["error"]["code"] == "rate_limited"
    assert int(responses[2].headers["Retry-After"]) >= 1


def test_sliding_window_frees_slots_after_a_minute():
    limiter = SlidingWindowLimiter()
    assert limiter.check("a", 1, now=0.0) is None
    assert limiter.check("a", 1, now=30.0) == pytest.approx(30.0)
    assert limiter.check("b", 1, now=30.0) is None  # limits are per identity
    assert limiter.check("a", 1, now=60.0) is None
    assert limiter.check("a", 0, now=60.0) is None  # 0 disables


def test_interrupted_incidents_are_failed_on_recovery():
    stuck, fresh = uuid.uuid4(), uuid.uuid4()
    for incident_id in (stuck, fresh):
        repositories.create_incident(incident_id, "o/r", "f" * 64, "TypeError", "")
    with session_scope() as session:
        session.execute(
            update(Incident).where(Incident.id == stuck).values(updated_at=datetime.now(UTC) - timedelta(hours=2))
        )
    assert incident_service.recover_interrupted_incidents() == 1
    assert repositories.get_incident(stuck)["error_category"] == "interrupted"
    assert repositories.get_incident(fresh)["status"] == "processing"
