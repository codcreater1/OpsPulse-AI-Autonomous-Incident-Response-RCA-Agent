from src.agent.nodes import decide_next, evaluate_quality_node
from src.agent.patching import format_code_window
from src.agent.state import initial_state
from tests.conftest import BAD_DIFF, GOOD_DIFF, SOURCE, TRACE, make_analysis


def _state(analysis, diff, with_source=True, iterations=1):
    st = initial_state("TypeError: 'NoneType' object is not subscriptable", TRACE, "o/r")
    st["affected_file"] = "src/app.py"
    if with_source:
        st["code_context"] = "FILE: src/app.py\n-----\n" + format_code_window(SOURCE.splitlines(), 1)
    st["root_cause_analysis"], st["suggested_patch"], st["iterations"] = analysis, diff, iterations
    return st


def test_good_patch_passes_gate():
    out = evaluate_quality_node(_state(make_analysis(GOOD_DIFF), GOOD_DIFF))
    assert out["confidence_score"] >= 0.85 and out["previous_feedback"] is None
    assert out["root_cause_analysis"]["control_flow"]["next_node"] == "NEON_SAVE_AND_GITHUB_PR"


def test_non_applicable_patch_fails_with_actionable_feedback():
    out = evaluate_quality_node(_state(make_analysis(BAD_DIFF), BAD_DIFF))
    assert out["confidence_score"] < 0.7
    assert "diff_applies" in out["previous_feedback"] and "verbatim" in out["previous_feedback"]


def test_overclaiming_llm_cannot_force_pass():
    out = evaluate_quality_node(_state(make_analysis(BAD_DIFF, confidence=1.0), BAD_DIFF))
    assert out["confidence_score"] < 0.85


def test_wrong_trigger_frame_is_penalised():
    out = evaluate_quality_node(_state(make_analysis(GOOD_DIFF, trigger="other.py:99"), GOOD_DIFF))
    assert out["confidence_score"] < 0.85 and "trigger_grounding" in out["previous_feedback"]


def test_invalid_json_scores_zero_and_missing_source_never_reaches_pr():
    assert evaluate_quality_node(_state({"error": "bad json"}, None))["confidence_score"] == 0.0
    out = evaluate_quality_node(_state(make_analysis(GOOD_DIFF), GOOD_DIFF, with_source=False))
    assert out["confidence_score"] < 0.85


def test_routing_rules():
    ctx = "src"
    assert decide_next(0.9, 1, ctx) == "PR"
    assert decide_next(0.5, 1, ctx) == "RETRY"
    assert decide_next(0.5, 3, ctx) == "REVIEW"
    assert decide_next(0.5, 1, None) == "REVIEW"
