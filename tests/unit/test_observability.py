import json
import logging
from typing import ClassVar

import pytest
from langchain_core.callbacks import BaseCallbackHandler

from src.integrations import observability as observability_module
from src.integrations.observability import build_run_config, mask_trace_data
from src.logging_config import JsonFormatter, incident_id_var, redact

_UNCACHED_HANDLER_LOOKUP = observability_module._callback_handler_class.__wrapped__

GH = "ghp_" + "A" * 36
GROQ = "gsk_" + "b" * 40


def test_redact_masks_known_credential_shapes():
    text = f"token {GH} key={GROQ} url=postgresql://app:hunter2@db.neon.tech/main pk-lf-1234abcd-ef"
    out = redact(text)
    for secret in (GH, GROQ, "hunter2", "pk-lf-1234abcd-ef"):
        assert secret not in out
    assert "postgresql://app:[REDACTED]@db.neon.tech/main" in out


def test_json_log_lines_carry_incident_id_and_are_redacted():
    record = logging.LogRecord("t", logging.ERROR, __file__, 1, "auth failed with %s", (GH,), None)
    token = incident_id_var.set("inc-123")
    try:
        line = json.loads(JsonFormatter().format(record))
    finally:
        incident_id_var.reset(token)
    assert line["incident_id"] == "inc-123" and GH not in line["message"]


def test_trace_mask_drops_long_content_but_keeps_short_metadata():
    data = {"incident_id": "inc-1", "prompt": "secret source code " * 50, "nested": [GH]}
    masked = mask_trace_data(data=data)
    assert masked["incident_id"] == "inc-1"
    assert masked["prompt"].startswith("[content omitted")
    assert GH not in masked["nested"][0]


def test_tracing_disabled_without_keys():
    config = build_run_config("inc-1", "o/r", "f" * 64)
    assert "callbacks" not in config and config["metadata"]["incident_id"] == "inc-1"


class _FakeSpan:
    def __init__(self, log, name):
        self.log, self.name = log, name

    def __enter__(self):
        self.log.append(("start", self.name))
        return self

    def __exit__(self, *exc):
        self.log.append(("end", self.name))
        return False

    def update(self, **kwargs):
        self.log.append(("update", self.name, kwargs))


class _RecordingHandler(BaseCallbackHandler):
    def __init__(self, public_key):
        self.public_key = public_key


class _FakeLangfuse:
    log: ClassVar[list] = []

    def __init__(self, **kwargs):
        assert kwargs["mask"] is not None  # masking is always installed
        _FakeLangfuse.log.append(("init", sorted(kwargs)))

    def start_as_current_observation(self, *, name, as_type, metadata=None):
        return _FakeSpan(self.log, name)

    def flush(self):
        raise RuntimeError("collector unreachable")


@pytest.fixture
def langfuse_enabled(monkeypatch, set_settings):
    from contextlib import nullcontext

    from src.integrations import observability

    set_settings(langfuse_public_key="pk-test", langfuse_secret_key="sk-test")
    _FakeLangfuse.log = []
    monkeypatch.setattr(observability, "Langfuse", _FakeLangfuse)
    monkeypatch.setattr(observability, "_callback_handler_class", lambda: _RecordingHandler)
    monkeypatch.setattr(observability, "propagate_attributes", lambda **kw: nullcontext())
    observability._client.cache_clear()
    yield _FakeLangfuse.log
    observability._client.cache_clear()


def test_enabled_tracing_creates_named_observations_and_survives_flush_failure(langfuse_enabled):
    from src.integrations.observability import build_run_config, flush_traces, incident_trace, observe

    with incident_trace("inc-1", "o/r", "f" * 64) as root:
        with observe("retrieval.historical_incidents", as_type="retriever") as span:
            span.update(metadata={"matches": 2})
        root.update(output={"status": "analysis_ready"})
    assert ("start", "incident.process") in langfuse_enabled
    assert ("start", "retrieval.historical_incidents") in langfuse_enabled
    (handler,) = build_run_config("inc-1", "o/r", "f" * 64)["callbacks"]
    assert isinstance(handler, _RecordingHandler) and handler.public_key == "pk-test"
    flush_traces()  # collector failure is logged, not raised


def test_unconstructible_client_degrades_to_disabled(monkeypatch, set_settings):
    from src.integrations import observability

    def broken(**_):
        raise ValueError("bad host")

    set_settings(langfuse_public_key="pk-test", langfuse_secret_key="sk-test")
    monkeypatch.setattr(observability, "Langfuse", broken)
    observability._client.cache_clear()
    try:
        with observability.observe("x") as span:
            span.update(output="ignored")
        assert "callbacks" not in observability.build_run_config("i", "o/r", "f" * 64)
    finally:
        observability._client.cache_clear()


def test_pipeline_runs_with_tracing_enabled(langfuse_enabled, client, fake_llm, source_fetch):
    from tests.unit.conftest import API_HEADERS
    from tests.unit.factories import incident_payload, make_analysis

    fake_llm([make_analysis()])
    body = client.post("/webhook/incident?wait=true", json=incident_payload(), headers=API_HEADERS).json()
    assert body["status"] == "analysis_ready"
    names = [entry[1] for entry in langfuse_enabled if entry[0] == "start"]
    assert {"incident.process", "retrieval.source_context", "evaluation.quality_gate"} <= set(names)


def test_missing_langchain_integration_disables_llm_tracing_but_not_the_app(langfuse_enabled, monkeypatch):
    import builtins

    from src.integrations import observability

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langfuse.langchain":
            raise ModuleNotFoundError("Please install langchain to use the Langfuse langchain integration")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(observability, "_callback_handler_class", _UNCACHED_HANDLER_LOOKUP)
    config = observability.build_run_config("inc-1", "o/r", "f" * 64)
    assert "callbacks" not in config and config["metadata"]["incident_id"] == "inc-1"
