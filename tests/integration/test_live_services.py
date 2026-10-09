"""Opt-in tests against real external services. Never part of the default `pytest` run.

    RUN_LIVE_TESTS=1 pytest tests/integration -v

Each test additionally skips when its own credential is missing. They use your real .env, cost a few
Groq tokens, and only READ from GitHub (no branches or PRs are created).
"""

import os

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import settings

pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="set RUN_LIVE_TESTS=1 to run live tests")


@pytest.mark.skipif(not settings.groq_api_key, reason="GROQ_API_KEY not set")
def test_groq_returns_schema_valid_rca_for_a_simple_incident():
    from src.agent.nodes import extract_json_object
    from src.agent.prompts import RCA_SYSTEM_PROMPT, build_rca_user_prompt
    from src.agent.schemas import RCAOutput
    from src.agent.state import initial_state
    from src.integrations.llm import invoke_json_model

    trace = (
        'Traceback (most recent call last):\n  File "/app/src/app.py", line 6, in load_user\n'
        "    name = profile[\"name\"]\nTypeError: 'NoneType' object is not subscriptable"
    )
    state = initial_state("live-1", "TypeError: 'NoneType' object is not subscriptable", trace, "o/r")
    state.update(affected_file="src/app.py", context_note="not retrieved in this test", history_status="ok")
    reply = invoke_json_model(
        [SystemMessage(content=RCA_SYSTEM_PROMPT), HumanMessage(content=build_rca_user_prompt(dict(state)))], 0.0, None
    )
    parsed = extract_json_object(reply.text)
    assert parsed is not None
    RCAOutput.model_validate(parsed)
    assert reply.input_tokens and reply.output_tokens  # provider reported usage


@pytest.mark.skipif(
    not (settings.github_token and os.getenv("LIVE_GITHUB_REPO")),
    reason="GITHUB_TOKEN and LIVE_GITHUB_REPO (owner/repo, also in ALLOWED_REPOSITORIES) required",
)
def test_github_source_context_can_be_read():
    from src.integrations.github import fetch_source_context

    repo = os.environ["LIVE_GITHUB_REPO"]
    path = os.getenv("LIVE_GITHUB_FILE", "README.md")
    ctx = fetch_source_context(repo, path, 1)
    assert ctx is not None and ctx.path.endswith(path) and "1 |" in ctx.window_text


@pytest.mark.skipif(not settings.database_url.startswith("postgres"), reason="DATABASE_URL is not PostgreSQL")
def test_database_answers():
    from src.db.client import ping_database

    ping_database()
