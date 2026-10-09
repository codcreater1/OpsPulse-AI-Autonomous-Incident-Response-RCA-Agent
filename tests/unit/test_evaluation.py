from src.agent.evaluation import BLOCKING_CHECKS, CHECK_WEIGHTS, EvaluationInput, evaluate
from src.agent.parsing import get_trigger_frame
from tests.unit.factories import BAD_DIFF, GOOD_DIFF, SOURCE_CONTEXT, TRACE, make_analysis

THRESHOLD = 0.85


def run(analysis, diff=GOOD_DIFF, with_source=True, history=None):
    return evaluate(
        EvaluationInput(
            analysis=analysis,
            patch=diff,
            stack_trace=TRACE,
            trigger=get_trigger_frame(TRACE),
            affected_file="src/app.py",
            code_context=SOURCE_CONTEXT.render() if with_source else None,
            historical_matches=history or [],
            max_changed_lines=40,
        ),
        THRESHOLD,
    )


def test_weights_are_normalised_and_blocking_checks_exist():
    assert abs(sum(CHECK_WEIGHTS.values()) - 1.0) < 1e-9
    assert set(CHECK_WEIGHTS) >= BLOCKING_CHECKS


def test_grounded_applicable_patch_passes():
    result = run(make_analysis())
    assert result.passed and result.score >= THRESHOLD and result.feedback is None
    assert all(c.fraction == 1.0 for name, c in result.checks.items() if name in BLOCKING_CHECKS)


def test_patch_that_does_not_apply_is_rejected_with_actionable_feedback():
    result = run(make_analysis(BAD_DIFF), BAD_DIFF)
    assert not result.passed
    assert "diff_applies [BLOCKING]" in result.feedback and "verbatim" in result.feedback


def test_overclaiming_model_cannot_force_a_pass():
    result = run(make_analysis(BAD_DIFF, confidence=1.0), BAD_DIFF)
    assert not result.passed


def test_fabricated_evidence_quote_blocks_even_with_high_total_score():
    result = run(make_analysis(quote='name = profile.get("name") or ""'))
    assert result.score >= 0.80  # everything else is fine...
    assert not result.passed  # ...but an invented quote is a blocking failure
    assert "quote not found verbatim" in result.checks["evidence_grounding"].detail


def test_quoting_source_code_that_was_never_retrieved_is_rejected():
    result = run(make_analysis(), with_source=False)
    assert not result.passed
    assert "was not retrieved" in result.checks["evidence_grounding"].detail
    assert result.checks["diff_applies"].fraction == 0.0


def test_history_quotes_are_only_valid_when_history_exists():
    analysis = make_analysis(quote="raise KeyError", quote_source="historical_incidents")
    assert "was not retrieved" in run(analysis).checks["evidence_grounding"].detail
    history = [
        {
            "match_reasons": ["same failure fingerprint"],
            "error_message": "x",
            "root_cause_summary": "raise KeyError here",
            "suggested_patch": "",
        }
    ]
    assert run(analysis, history=history).checks["evidence_grounding"].fraction == 1.0


def test_wrong_trigger_frame_is_penalised():
    result = run(make_analysis(trigger="other.py:99"))
    assert not result.passed and "trigger_grounding" in result.feedback


def test_ungrounded_affected_file_is_reported():
    analysis = make_analysis()
    analysis["affected_files"] = ["src/app.py", "src/billing/invoice.py"]
    check = run(analysis).checks["affected_files_grounding"]
    assert check.fraction == 0.5 and "invoice.py" in check.detail


def test_diff_for_a_different_file_is_blocking():
    diff = GOOD_DIFF.replace("src/app.py", "src/other.py")
    result = run(make_analysis(diff), diff)
    assert not result.passed and result.checks["diff_wellformed"].fraction < 1.0


def test_schema_errors_are_listed():
    analysis = make_analysis()
    del analysis["uncertainties"]
    analysis["incident_summary"]["severity"] = "SEVERE"
    result = run(analysis)
    assert not result.passed
    assert "uncertainties" in result.checks["schema"].detail and "severity" in result.checks["schema"].detail


def test_invalid_json_marker_scores_zero_schema():
    result = run({"output_error": "the model did not return a valid JSON object"}, diff=None)
    assert result.checks["schema"].fraction == 0.0 and not result.passed


def test_model_declaring_insufficient_evidence_never_passes():
    result = run(make_analysis(evidence_sufficient=False))
    assert not result.passed and result.evidence_sufficient is False


def test_oversized_patch_loses_minimality_points():
    big = GOOD_DIFF.replace(
        '+        raise ValueError("missing profile")\n', "".join(f"+        x{i} = {i}\n" for i in range(90))
    )
    assert run(make_analysis(big), big).checks["patch_minimal"].fraction == 0.0
