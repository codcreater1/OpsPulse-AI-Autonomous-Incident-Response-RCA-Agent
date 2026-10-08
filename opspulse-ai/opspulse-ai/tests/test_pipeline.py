import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import src.agent.nodes as nodes
import src.main as main
from src.agent.patching import format_code_window
from src.agent.state import initial_state
from src.db.client import get_incident
from src.integrations.github import SourceContext
from tests.conftest import BAD_DIFF, GOOD_DIFF, SOURCE, TRACE, make_analysis


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    def invoke(self, messages, config=None):
        self.prompts.append(messages[-1].content)
        return SimpleNamespace(content=json.dumps(self.replies.pop(0)))


@pytest.fixture
def github(monkeypatch):
    ctx = SourceContext("src/app.py", "abc123456789", 1, 13, 6, format_code_window(SOURCE.splitlines(), 1), [])
    monkeypatch.setattr("src.integrations.github.fetch_source_context", lambda *a, **k: ctx)
    created = []
    monkeypatch.setattr(main, "create_fix_pull_request",
                        lambda **kw: created.append(kw) or {"pr_url": "https://github.com/o/r/pull/7", "pr_number": 7, "branch": "opspulse/fix-x"})
    return created


def test_self_correction_loop_then_pr(monkeypatch, github):
    llm = FakeLLM([make_analysis(BAD_DIFF), make_analysis(GOOD_DIFF)])
    monkeypatch.setattr(nodes, "_get_llm", lambda temperature: llm)
    client = TestClient(main.app)
    resp = client.post("/webhook/incident?wait=true",
                       json={"error_message": "TypeError: 'NoneType' object is not subscriptable", "stack_trace": TRACE, "repo_name": "o/r"})
    body = resp.json()
    assert body["status"] == "pr_created" and body["iterations"] == 2 and body["confidence_score"] >= 0.85
    assert "PREVIOUS_FEEDBACK" in llm.prompts[1] and "diff_applies" in llm.prompts[1]
    assert github[0]["file_path"] == "src/app.py"
    row = get_incident(__import__("uuid").UUID(body["incident_id"]))
    assert row["status"] == "pr_created" and row["pr_number"] == 7
    assert row["root_cause_analysis"]["execution_metadata"]["iteration"] == 2


def test_gives_up_after_three_iterations_and_flags_human_review(monkeypatch, github):
    llm = FakeLLM([make_analysis(BAD_DIFF)] * 3)
    monkeypatch.setattr(nodes, "_get_llm", lambda temperature: llm)
    body = TestClient(main.app).post("/webhook/incident?wait=true",
        json={"error_message": "TypeError: x", "stack_trace": TRACE, "repo_name": "o/r"}).json()
    assert body["status"] == "needs_review" and body["iterations"] == 3 and not github


def test_duplicate_pr_guard_and_history_lookup(monkeypatch, github):
    llm = FakeLLM([make_analysis(GOOD_DIFF)] * 2)
    monkeypatch.setattr(nodes, "_get_llm", lambda temperature: llm)
    client = TestClient(main.app)
    payload = {"error_message": "TypeError: x", "stack_trace": TRACE, "repo_name": "o/r"}
    assert client.post("/webhook/incident?wait=true", json=payload).json()["status"] == "pr_created"
    assert client.post("/webhook/incident?wait=true", json=payload).json()["status"] == "pr_skipped_duplicate"
    assert "match=exact" in llm.prompts[1] and len(github) == 1


def test_invalid_json_from_llm_is_handled(monkeypatch, github):
    class Junk:
        def invoke(self, messages, config=None):
            return SimpleNamespace(content="sorry, I cannot help")
    monkeypatch.setattr(nodes, "_get_llm", lambda temperature: Junk())
    body = TestClient(main.app).post("/webhook/incident?wait=true",
        json={"error_message": "TypeError: x", "stack_trace": TRACE, "repo_name": "o/r"}).json()
    assert body["status"] == "needs_review" and body["confidence_score"] == 0.0


def test_webhook_validation_and_secret(monkeypatch):
    client = TestClient(main.app)
    assert client.post("/webhook/incident", json={"error_message": "x", "repo_name": "bad repo"}).status_code == 422
    object.__setattr__(main.settings, "webhook_secret", "s3cret")
    try:
        assert client.post("/webhook/incident", json={"error_message": "x", "repo_name": "o/r"}).status_code == 401
        assert client.get("/healthz").status_code == 200
    finally:
        object.__setattr__(main.settings, "webhook_secret", "")


def test_async_webhook_returns_202(monkeypatch, github):
    monkeypatch.setattr(nodes, "_get_llm", lambda temperature: FakeLLM([make_analysis(GOOD_DIFF)]))
    client = TestClient(main.app)
    resp = client.post("/webhook/incident", json={"error_message": "TypeError: x", "stack_trace": TRACE, "repo_name": "o/r"})
    assert resp.status_code == 202
    assert client.get(f"/incidents/{resp.json()['incident_id']}").json()["status"] == "pr_created"
