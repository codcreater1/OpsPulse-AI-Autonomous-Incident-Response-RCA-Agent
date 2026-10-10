"""Reviewer notifications and merging of partial evaluation reports."""

import pytest
import requests

from evals.merge_reports import IncompatibleReportsError, merge
from src.config import ConfigError, _https_url
from src.integrations import notify
from tests.unit.conftest import API_HEADERS
from tests.unit.factories import incident_payload, make_analysis


class _Recorder:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def __call__(self, url, json, timeout):
        self.calls.append((url, json))
        if self.fail:
            raise requests.ConnectionError("unreachable")
        return type("R", (), {"raise_for_status": lambda self: None})()


@pytest.fixture
def webhook(monkeypatch, set_settings):
    set_settings(notify_webhook_url="https://hooks.example.test/x", public_base_url="https://ops.example.test")
    recorder = _Recorder()
    monkeypatch.setattr(notify.requests, "post", recorder)
    return recorder


def test_awaiting_approval_sends_a_content_free_message(client, fake_llm, source_fetch, set_settings, webhook):
    set_settings(enable_github_remediation=True, github_token="t", require_remediation_approval=True)
    analysis = make_analysis()
    analysis["incident_summary"]["title"] = "Crash <!channel> @here in load_user"
    fake_llm([analysis])
    body = client.post("/webhook/incident?wait=true", json=incident_payload(), headers=API_HEADERS).json()
    assert body["status"] == "awaiting_approval"
    ((url, payload),) = webhook.calls
    text = payload["text"]
    assert url == "https://hooks.example.test/x" and "awaiting approval" in text
    assert "https://ops.example.test/console" in text and body["incident_id"] in text
    assert "@" not in text and "<" not in text  # no pings or link markup from model text
    assert "profile" not in text and "Traceback" not in text and "---" not in text  # no code, trace or patch


def test_statuses_not_selected_are_not_notified(client, fake_llm, source_fetch, webhook):
    fake_llm([make_analysis()])
    body = client.post("/webhook/incident?wait=true", json=incident_payload(), headers=API_HEADERS).json()
    assert body["status"] == "analysis_ready" and webhook.calls == []


def test_delivery_failure_never_breaks_processing(client, source_fetch, monkeypatch, set_settings):
    set_settings(notify_webhook_url="https://hooks.example.test/x")
    monkeypatch.setattr(notify.requests, "post", _Recorder(fail=True))
    body = client.post("/webhook/incident?wait=true", json=incident_payload(), headers=API_HEADERS).json()
    assert body["status"] == "failed"  # (no Groq key in tests) - the notification failure did not raise


def test_webhook_url_must_be_https(monkeypatch):
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "http://hooks.example.test/x")
    with pytest.raises(ConfigError):
        _https_url("NOTIFY_WEBHOOK_URL")


def _report(started, results, model="m"):
    return {
        "mode": "live",
        "dataset_version": "d",
        "run_metadata": {"model": model},
        "started_at": started,
        "results": results,
    }


def _case(case_id, failed):
    return {
        "case_id": case_id,
        "workflow_status": "failed" if failed else "accepted",
        "error_category": "llm_rate_limited" if failed else None,
        "expected": {"root_cause_category": "x", "inconclusive": False, "relevant_files": []},
        "predicted_category": None if failed else "x",
        "gate_passed": not failed,
        "declared_insufficient": False,
        "observed_quotes": 0,
        "grounded_quotes": 0,
        "affected_files": [],
        "grounded_files": 0,
        "attempts": [],
        "wall_ms": 1,
    }


def test_merge_takes_evaluated_results_over_quota_failures():
    first = _report("t1", [_case("a", False), _case("b", True)])
    second = _report("t2", [_case("b", False)])
    merged = merge([first, second])
    assert merged["metrics"]["cases_not_evaluated"] == [] and merged["metrics"]["cases"] == 2
    assert merged["merged_from"] == ["t1", "t2"]


def test_merge_refuses_different_configurations():
    with pytest.raises(IncompatibleReportsError):
        merge([_report("t1", [_case("a", False)]), _report("t2", [_case("b", False)], model="other")])
