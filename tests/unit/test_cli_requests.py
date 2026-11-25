"""What the CLI sends and prints for each command, against a recording transport (no application needed)."""

import json

from src import cli


def run(*argv, reply=None, status=200):
    sent = []

    def transport(method, url, headers, body):
        sent.append((method, url, headers, json.loads(body) if body else None))
        return status, json.dumps(reply if reply is not None else {}).encode()

    code = cli.main(["--url", "http://x", "--key", "k", *argv], transport=transport)
    return code, sent


def test_submit_sends_the_repository_error_trace_and_the_chosen_incident_id(capsys, tmp_path):
    trace = tmp_path / "t.txt"
    trace.write_text("Traceback...", encoding="utf-8")
    code, sent = run(
        "submit",
        "--repo",
        "o/r",
        "--error",
        "KeyError: 'x'",
        "--trace-file",
        str(trace),
        "--id",
        "7" * 8 + "-0000-4000-8000-" + "0" * 12,
        reply={"incident_id": "abc", "status": "queued"},
    )
    ((method, url, headers, body),) = sent
    assert code == 0 and (method, url) == ("POST", "http://x/webhook/incident") and headers["X-API-Key"] == "k"
    assert body == {
        "repo_name": "o/r",
        "error_message": "KeyError: 'x'",
        "stack_trace": "Traceback...",
        "incident_id": "77777777-0000-4000-8000-000000000000",
    }
    assert "accepted: abc" in capsys.readouterr().out


def test_wait_adds_the_query_and_prints_the_analysis_when_there_is_one(capsys):
    reply = {
        "incident_id": "abc",
        "status": "analysis_ready",
        "analysis": {"root_cause_category": "logic_error"},
        "quality_score": 0.9,
    }
    code, sent = run("submit", "--repo", "o/r", "--error", "boom", "--wait", reply=reply)
    assert (
        sent[0][1] == "http://x/webhook/incident?wait=true" and "logic_error" in capsys.readouterr().out and code == 0
    )


def test_list_prints_a_cursor_hint_only_when_there_is_more(capsys):
    item = {
        "incident_id": "i1",
        "status": "awaiting_approval",
        "quality_score": 0.9,
        "repo_name": "o/r",
        "affected_file": None,
    }
    run("list", "--limit", "1", "--status", "awaiting_approval", reply={"items": [item], "next_cursor": "CUR"})
    out = capsys.readouterr().out
    assert "awaiting approval" in out and "(more available; cursor CUR)" in out
    run("list", reply={"items": [], "next_cursor": None})
    assert "no incidents match" in capsys.readouterr().out


def test_the_list_request_carries_the_limit_and_the_status_filter():
    _, sent = run("list", "--limit", "5", "--status", "failed", reply={"items": []})
    assert sent[0][1] == "http://x/incidents?limit=5&status=failed"


def test_retry_posts_to_the_retry_endpoint_and_reports_the_new_status(capsys):
    code, sent = run("retry", "abc", reply={"incident_id": "abc", "status": "queued"})
    assert (sent[0][0], sent[0][1]) == ("POST", "http://x/incidents/abc/retry") and code == 0
    assert "re-queued: abc  status: queued" in capsys.readouterr().out


def test_an_incident_with_a_pull_request_shows_it_and_the_root_cause_hypothesis(capsys):
    incident = {
        "incident_id": "abc",
        "status": "pr_opened",
        "pr_url": "https://github.com/o/r/pull/9",
        "analysis": {"diagnostic_chain": {"primary_root_cause": {"technical_explanation": "x is None"}}},
    }
    run("show", "abc", reply=incident)
    out = capsys.readouterr().out
    assert (
        "pull request  https://github.com/o/r/pull/9" in out
        and "root cause (model hypothesis):" in out
        and "x is None" in out
    )


def test_an_answer_lists_quotes_that_could_not_be_verified(capsys):
    reply = {
        "answer": "a",
        "source": "model",
        "unverified_quotes": ["not real"],
        "disclaimer": "model text, not verified",
    }
    run("ask", "abc", "why?", reply=reply)
    out = capsys.readouterr().out
    assert "not in the record: not real" in out and "model text, not verified" in out


def test_json_prints_the_raw_response_instead_of_the_summary(capsys):
    code = cli.main(
        ["--url", "http://x", "--key", "k", "--json", "retry", "abc"],
        transport=lambda *a: (200, b'{"incident_id": "abc", "status": "queued"}'),
    )
    assert code == 0 and json.loads(capsys.readouterr().out) == {"incident_id": "abc", "status": "queued"}
