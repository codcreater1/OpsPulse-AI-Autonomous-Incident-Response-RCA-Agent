import groq
import httpx
import pytest

from src.integrations import llm
from src.integrations.llm import LLMError, invoke_json_model

_REQUEST = httpx.Request("POST", "https://api.groq.test/openai/v1/chat/completions")


def _status_error(cls, status, code=None):
    body = {"error": {"code": code, "message": "x"}} if code else None
    return cls("provider said no", response=httpx.Response(status, request=_REQUEST), body=body)


class Raising:
    def __init__(self, exc):
        self.exc = exc

    def invoke(self, messages, config=None):
        raise self.exc


@pytest.mark.parametrize(
    "exc,category",
    [
        (_status_error(groq.RateLimitError, 429), "rate_limited"),
        (_status_error(groq.AuthenticationError, 401), "auth"),
        (_status_error(groq.NotFoundError, 404), "model_unavailable"),
        (_status_error(groq.BadRequestError, 400, "model_decommissioned"), "model_unavailable"),
        (_status_error(groq.BadRequestError, 400, "context_length_exceeded"), "bad_request"),
        (_status_error(groq.InternalServerError, 503), "provider_error"),
        (groq.APITimeoutError(request=_REQUEST), "timeout"),
        (groq.APIConnectionError(request=_REQUEST), "connection"),
    ],
)
def test_provider_errors_are_classified(monkeypatch, exc, category):
    monkeypatch.setattr(llm, "get_chat_model", lambda temperature: Raising(exc))
    with pytest.raises(LLMError) as info:
        invoke_json_model([], 0.0, None)
    assert info.value.category == category


def test_json_validation_failure_is_a_failed_attempt_not_an_outage(monkeypatch):
    exc = _status_error(groq.BadRequestError, 400, "json_validate_failed")
    monkeypatch.setattr(llm, "get_chat_model", lambda temperature: Raising(exc))
    assert invoke_json_model([], 0.0, None).text == ""


def test_missing_api_key_is_reported_as_not_configured():
    llm.get_chat_model.cache_clear()
    with pytest.raises(LLMError) as info:
        llm.get_chat_model(0.0)
    assert info.value.category == "not_configured"
