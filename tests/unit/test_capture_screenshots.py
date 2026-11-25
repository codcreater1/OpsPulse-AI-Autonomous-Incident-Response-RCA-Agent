"""The screenshot script's decisions that do not need a browser: which incident to shoot, how it waits, how it fails."""

import pytest

from scripts import capture_screenshots as cap


def _incidents(*rows):
    return {"items": [{"incident_id": i, "status": s, "iterations": n} for i, s, n in rows]}


def test_the_incident_with_the_longest_attempt_history_is_chosen(monkeypatch):
    monkeypatch.setattr(
        cap, "_get", lambda url, key="": _incidents(("a", "analysis_ready", 1), ("b", "analysis_ready", 3))
    )
    assert cap.pick_incident("http://x") == "b"


def test_on_equal_history_a_needs_review_incident_wins_because_it_shows_more(monkeypatch):
    monkeypatch.setattr(
        cap, "_get", lambda url, key="": _incidents(("a", "analysis_ready", 2), ("b", "needs_review", 2))
    )
    assert cap.pick_incident("http://x") == "b"


def test_the_status_filter_and_an_empty_list_give_none_not_an_error(monkeypatch):
    monkeypatch.setattr(cap, "_get", lambda url, key="": _incidents(("a", "analysis_ready", 2)))
    assert cap.pick_incident("http://x", "awaiting_approval") is None
    monkeypatch.setattr(cap, "_get", lambda url, key="": {"items": []})
    assert cap.pick_incident("http://x") is None


def test_the_demo_key_is_sent_to_the_incident_list(monkeypatch):
    seen = []
    monkeypatch.setattr(cap, "_get", lambda url, key="": seen.append((url, key)) or {"items": []})
    cap.pick_incident("http://x")
    assert seen == [("http://x/incidents?limit=50", cap.DEMO_KEY)]


def test_no_browser_is_exit_code_2_and_starts_no_server(monkeypatch, capsys):
    monkeypatch.setattr(cap, "find_browser", lambda: None)
    monkeypatch.setattr(cap.subprocess, "Popen", lambda *a, **k: pytest.fail("must not start the demo server"))
    assert cap.main([]) == 2 and "no Edge/Chrome/Chromium" in capsys.readouterr().err


def test_a_server_that_never_becomes_healthy_is_a_one_line_exit(monkeypatch):
    monkeypatch.setattr(cap, "_get", lambda url, key="": {"status": "starting"})
    monkeypatch.setattr(cap.time, "sleep", lambda s: None)
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr(cap.time, "time", lambda: next(clock))
    with pytest.raises(SystemExit, match="did not start"):
        cap.wait_ready("http://x", seconds=30)


def test_waiting_for_a_server_that_answers_but_is_not_ready_does_not_spin(monkeypatch):
    # Regression: only a connection error slept, so a server that answered "starting" was polled in a busy loop.
    sleeps = []
    monkeypatch.setattr(cap, "_get", lambda url, key="": {"status": "starting"})
    monkeypatch.setattr(cap.time, "sleep", lambda s: sleeps.append(s))
    clock = iter(range(0, 1000, 1))
    monkeypatch.setattr(cap.time, "time", lambda: next(clock))
    with pytest.raises(SystemExit):
        cap.wait_ready("http://x", seconds=5)
    assert sleeps, "the wait loop must pause between polls"


def test_ready_server_returns_at_once(monkeypatch):
    monkeypatch.setattr(cap, "_get", lambda url, key="": {"status": "ok"})
    cap.wait_ready("http://x")


def test_the_browser_command_is_headless_motionless_and_writes_to_the_requested_file(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(cap.subprocess, "run", lambda command, **kwargs: seen.update(command=command, kwargs=kwargs))
    out = tmp_path / "sub" / "shot.png"
    cap.shoot("/usr/bin/chrome", "http://x/console?theme=dark", out, (1360, 900))
    command = seen["command"]
    assert out.parent.is_dir() and f"--screenshot={out}" in command and command[-1] == "http://x/console?theme=dark"
    assert (
        "--headless=new" in command
        and "--force-prefers-reduced-motion" in command
        and "--window-size=1360,900" in command
    )
    assert seen["kwargs"]["check"] is True and seen["kwargs"]["timeout"] == 120


def test_find_browser_prefers_a_known_path_then_the_path_lookup(monkeypatch):
    monkeypatch.setattr(cap.os.path, "exists", lambda p: p == "/usr/bin/chromium")
    assert cap.find_browser() == "/usr/bin/chromium"
    monkeypatch.setattr(cap.os.path, "exists", lambda p: False)
    monkeypatch.setattr(cap.shutil, "which", lambda name: "/opt/bin/chrome" if name == "chrome" else None)
    assert cap.find_browser() == "/opt/bin/chrome"
    monkeypatch.setattr(cap.shutil, "which", lambda name: None)
    assert cap.find_browser() is None
