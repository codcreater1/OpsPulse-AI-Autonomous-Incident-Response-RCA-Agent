"""Deterministic guidance: every sentence comes from stored fields; no model, no claim of correctness."""

from datetime import UTC, datetime

import pytest

from src.agent.evaluation import CHECK_WEIGHTS
from src.errors import ErrorCategory
from src.services.guidance import CATEGORY_GUIDE, CHECK_ADVICE, STATUS_GUIDE, build_guidance, patch_facts
from tests.unit.conftest import API_HEADERS
from tests.unit.factories import GOOD_DIFF, incident_payload, make_analysis

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _incident(**overrides):
    return {"status": "needs_review", "quality_score": 0.5, "iterations": 1, "analysis": {}, **overrides}


def test_every_gate_check_and_error_category_has_guidance():
    assert set(CHECK_WEIGHTS) <= set(CHECK_ADVICE)  # a new check must come with advice
    for category in ErrorCategory:
        assert category.value in CATEGORY_GUIDE, f"no guidance for {category.value}"
    assert {"queued", "processing", "failed", "needs_review", "awaiting_approval", "pr_failed"} <= set(STATUS_GUIDE)


def test_failed_provider_call_explains_the_cause_and_offers_retry():
    guide = build_guidance(_incident(status="failed", error_category="llm_request_too_large"), NOW)
    assert guide["state"] == "blocked" and "per-minute token cap" in guide["explanation"]
    texts = " ".join(step["text"] for step in guide["next_steps"])
    assert "LLM_MAX_OUTPUT_TOKENS" in texts and "Retry" in texts


def test_failed_checks_are_listed_blocking_first_with_advice():
    checks = {
        "self_assessment": {"score": 0.02, "max": 0.05, "blocking": False, "detail": "low"},
        "diff_applies": {"score": 0.0, "max": 0.2, "blocking": True, "detail": "hunk 1 not found"},
        "schema": {"score": 0.1, "max": 0.1, "blocking": True, "detail": "ok"},
    }
    guide = build_guidance(_incident(analysis={"evaluation": {"checks": checks}}), NOW)
    assert [c["name"] for c in guide["failed_checks"]] == ["diff_applies", "self_assessment"]
    assert guide["failed_checks"][0]["blocking"] and "apply the idea by hand" in guide["failed_checks"][0]["advice"]
    assert any("diff_applies" in s["text"] for s in guide["next_steps"])


def test_same_failure_in_every_attempt_and_truncation_are_surfaced():
    attempts = [
        {
            "gate_passed": False,
            "failed_checks": ["diff_applies", "self_assessment"],
            "truncated": True,
            "input_tokens": 100,
            "output_tokens": 50,
        },
        {"gate_passed": False, "failed_checks": ["diff_applies"], "input_tokens": 100, "output_tokens": 50},
    ]
    guide = build_guidance(_incident(analysis={"attempts": attempts}), NOW)
    assert any("diff_applies" in fact and "every attempt" in fact for fact in guide["facts"])
    assert any("300 provider tokens" in fact for fact in guide["facts"])
    assert any("LLM_MAX_OUTPUT_TOKENS" in s["text"] for s in guide["next_steps"])


def test_waiting_and_approval_states():
    deferred = build_guidance(_incident(status="queued", available_at="2026-10-10T12:30:00+00:00"), NOW)
    assert deferred["state"] == "waiting" and "12:30 UTC" in deferred["next_steps"][0]["text"]
    approval = build_guidance(_incident(status="awaiting_approval"), NOW)
    assert approval["state"] == "attention" and any(
        "bound to this exact patch" in s["text"] for s in approval["next_steps"]
    )


def test_patch_facts_are_counts_from_the_diff_only():
    facts = patch_facts(GOOD_DIFF)
    assert facts and facts["parsable"] and facts["hunks"] >= 1 and facts["added"] >= 1
    assert patch_facts(None) is None and patch_facts("garbage") == {"parsable": False}


def test_unknown_status_is_reported_not_guessed():
    guide = build_guidance(_incident(status="something_new"), NOW)
    assert guide["headline"] == "Unknown status" and guide["state"] == "attention"


def test_guidance_endpoint(client, fake_llm, source_fetch):
    fake_llm([make_analysis()])
    incident_id = client.post("/webhook/incident?wait=true", json=incident_payload(), headers=API_HEADERS).json()[
        "incident_id"
    ]
    resp = client.get(f"/incidents/{incident_id}/guidance", headers=API_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] in {"ok", "attention"} and body["headline"] and isinstance(body["next_steps"], list)
    assert client.get(f"/incidents/{incident_id}/guidance").status_code == 401
    missing = client.get("/incidents/00000000-0000-0000-0000-000000000000/guidance", headers=API_HEADERS)
    assert missing.status_code == 404


@pytest.mark.parametrize("status", sorted(STATUS_GUIDE))
def test_every_status_produces_a_headline(status):
    assert build_guidance(_incident(status=status), NOW)["headline"]
