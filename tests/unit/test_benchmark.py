"""Regression comparison, calibration metrics and the adversarial dataset."""

import json

import pytest

from evals.compare_reports import main as compare_main
from evals.compare_reports import regressions
from evals.dataset import load_rca_dataset
from evals.harness import ScriptedModel, run_case
from evals.metrics import calibration, compute_metrics
from evals.run_rca import DATASET_FILES


def _result(cat_ok=True, inconclusive=False, gate=True, conf=0.8, quotes=(2, 2)):
    return {
        "case_id": "c",
        "workflow_status": "accepted" if gate else "needs_review",
        "error_category": None,
        "expected": {"root_cause_category": "missing_key", "inconclusive": inconclusive, "relevant_files": []},
        "predicted_category": "missing_key" if cat_ok else "type_error",
        "gate_passed": gate,
        "declared_insufficient": False,
        "observed_quotes": quotes[0],
        "grounded_quotes": quotes[1],
        "affected_files": [],
        "grounded_files": 0,
        "attempts": [],
        "wall_ms": 1,
        "model_confidence": conf,
        "quality_score": 0.9 if gate else 0.4,
    }


def _report(results, model="m"):
    return {
        "dataset_version": "d",
        "run_metadata": {"model": model, "prompt_version": "p"},
        "metrics": compute_metrics(results),
        "results": results,
    }


def test_calibration_brier_and_bins():
    results = [_result(cat_ok=True, conf=0.9), _result(cat_ok=False, conf=0.9), _result(cat_ok=True, conf=0.3)]
    cal = calibration(results, "model_confidence")
    assert cal["samples"] == 3
    assert cal["brier"] == pytest.approx(((0.9 - 1) ** 2 + 0.9**2 + (0.3 - 1) ** 2) / 3, abs=1e-4)
    high = next(b for b in cal["bins"] if b["range"] == "0.85-1.00")
    assert high["n"] == 2 and high["accuracy"] == 0.5  # overconfident: claims 0.9, right half the time


def test_unsupported_acceptance_counts_inconclusive_and_unverifiable_quotes():
    results = [_result(inconclusive=True, gate=True), _result(quotes=(2, 1), gate=False), _result()]
    metric = compute_metrics(results)["unsupported_acceptance_rate"]
    assert (metric["numerator"], metric["denominator"]) == (1, 2)


def test_regression_detection_respects_direction_and_tolerance():
    base = _report([_result(), _result()])
    worse = _report([_result(), _result(cat_ok=False)])
    assert regressions(base, worse, 0.0) == [
        "category_accuracy: 1.000 -> 0.500",
        "false_acceptance_rate: 0.000 -> 0.500",
    ]
    assert regressions(base, worse, 0.6) == []
    assert regressions(worse, base, 0.0) == []  # improvements are never regressions


def test_compare_cli_exit_codes(tmp_path):
    base, worse = tmp_path / "base.json", tmp_path / "worse.json"
    base.write_text(json.dumps(_report([_result()])), encoding="utf-8")
    worse.write_text(json.dumps(_report([_result(cat_ok=False)])), encoding="utf-8")
    assert compare_main([str(base), str(worse)]) == 0
    assert compare_main([str(base), str(worse), "--fail-on-regression"]) == 1
    other = tmp_path / "other.json"
    other.write_text(json.dumps({**_report([_result()]), "dataset_version": "x"}), encoding="utf-8")
    assert compare_main([str(base), str(other)]) == 2


def test_adversarial_bait_is_rejected_by_the_gate_in_mock_mode():
    cases = {c.id: c for c in load_rca_dataset(DATASET_FILES["adversarial"]).cases}

    def run(case_id):
        model = ScriptedModel(cases[case_id])
        return run_case(cases[case_id], lambda temperature: model)

    for case_id in ("adv-fabricated-line", "adv-foreign-file-patch", "adv-injected-approval", "adv-deploy-drift"):
        result = run(case_id)
        first = result["attempts"][0]
        assert first["gate_passed"] is False and first["failed_checks"], case_id  # bait rejected, with reasons
    for case_id in ("adv-guess-without-source", "adv-truncated-trace"):
        assert run(case_id)["gate_passed"] is False
    # documented blind spot: grounded but wrong diagnosis is accepted
    blind = run("adv-misleading-history-blind-spot")
    assert blind["gate_passed"] and blind["predicted_category"] != blind["expected"]["root_cause_category"]


def test_repeated_runs_report_run_to_run_consistency():
    from evals.metrics import consistency

    stable = [_result(), _result()]
    flaky = [_result(), _result(cat_ok=False, gate=False)]
    for r in stable:
        r["case_id"] = "stable"
    for r in flaky:
        r["case_id"] = "flaky"
    out = consistency(stable + flaky)
    assert out and out["cases_repeated"] == 2
    assert out["stable_outcome_rate"]["numerator"] == 1  # only "stable" never changed
    assert out["per_case"]["flaky"] == {"runs": 2, "accepted": 1, "correct_category": 1, "distinct_outcomes": 2}
    assert consistency([_result()]) is None  # nothing repeated, nothing reported


def test_repeat_flag_runs_each_case_n_times_in_mock_mode(tmp_path):
    from evals.run_rca import run

    report = run("mock", ["adv-fabricated-line"], tmp_path, dataset_name="adversarial", repeat=3)
    assert [r["run"] for r in report["results"]] == [1, 2, 3]
    assert report["metrics"]["consistency"]["per_case"]["adv-fabricated-line"]["runs"] == 3
    assert "Run-to-run consistency" in (tmp_path / report["paths"][1].split("\\")[-1].split("/")[-1]).read_text(
        encoding="utf-8"
    )
