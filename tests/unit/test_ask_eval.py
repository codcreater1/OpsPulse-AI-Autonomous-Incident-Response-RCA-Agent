"""The assistant evaluation harness and the validation properties it measures."""

import pytest

from evals.ask_eval import main, run
from src.services.ask_service import APPROVAL_NOTICE, parse_answer, record_text, unverified_quotes


def test_mock_evaluation_measures_every_layer_and_all_checks_hold():
    report = run("mock")
    metrics = report["metrics"]
    for name in (
        "rules_intent_accuracy",
        "rules_content_correctness",
        "rules_answered_without_model",
        "grounded_answers_pass",
        "fabricated_quotes_flagged",
        "uncited_answers_flagged",
        "unanswerable_abstained",
        "approval_advice_blocked",
    ):
        assert metrics[name]["denominator"] > 0, name
        assert metrics[name]["value"] == 1.0, f"{name}: {metrics[name]}"
    assert metrics["degraded_rate"]["value"] == 0.0


def test_cli_exit_codes_follow_thresholds(tmp_path):
    ok = main(["--mode", "mock", "--out", str(tmp_path), "--min", "rules_intent_accuracy=1.0"])
    assert ok == 0
    assert main(["--mode", "mock", "--out", str(tmp_path), "--min", "rules_intent_accuracy=1.1"]) == 1
    assert list(tmp_path.glob("ask-mock-*.json")) and list(tmp_path.glob("ask-mock-*.md"))


@pytest.mark.parametrize(
    "answer",
    [
        "You should approve and merge this now.",
        "It is safe to merge.",
        "Please approve it, the evidence is solid.",
        "I recommend to approve the patch.",
        "Just approve this.",
    ],
)
def test_approval_advice_is_replaced_and_ungrounded(answer):
    reply = {"answer": answer, "answerable": True, "cited_sections": ["summary"]}
    out = parse_answer(__import__("json").dumps(reply), {"summary": "x"})
    assert out["flags"] == ["approval_advice"] and out["answer"] == APPROVAL_NOTICE and out["grounded"] is False


@pytest.mark.parametrize(
    "answer",
    [
        "Nothing was merged; the pull request is a draft.",
        "The approval is bound to the patch SHA-256.",
        "A reviewer must decide whether the patch is acceptable.",
        "The gate checks grounding, not that the fix is correct.",
    ],
)
def test_neutral_sentences_about_approval_are_not_flagged(answer):
    reply = {"answer": answer, "answerable": True, "cited_sections": ["summary"]}
    out = parse_answer(__import__("json").dumps(reply), {"summary": "x"})
    assert out["flags"] == [] and out["grounded"] is True


def test_quotes_are_verified_against_decoded_record_text_not_its_json_rendering():
    record = {"analysis": {"evidence": [{"quote": 'os.environ["STRIPE_API_KEY"]'}]}, "suggested_patch": "+x = 1\n"}
    sections = {"evidence": '[{"quote": "os.environ[\\"STRIPE_API_KEY\\"]"}]'}  # what the prompt shows: JSON-escaped
    text = record_text(record)
    assert 'os.environ["STRIPE_API_KEY"]' in text and "+x = 1" in text
    assert unverified_quotes('it reads `os.environ["STRIPE_API_KEY"]`', sections, text) == []
    assert unverified_quotes('it reads `os.environ["STRIPE_API_KEY"]`', sections) != []  # the old behaviour was wrong
