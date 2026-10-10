"""Compare evaluation reports side by side, and fail on regressions against a baseline.

    python -m evals.compare_reports BASELINE.json CANDIDATE.json [MORE.json ...]
    python -m evals.compare_reports BASELINE.json CANDIDATE.json --fail-on-regression [--tolerance 0.02]

The first report is the baseline. A regression is a quality metric moving in its bad direction by more than
`--tolerance` (absolute). Cost/latency figures are reported but never fail the comparison, and metrics with no
data (None) in either report are skipped. Comparing reports from different datasets is refused.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

# metric -> True if higher is better
QUALITY_METRICS: dict[str, bool] = {
    "category_accuracy": True,
    "evidence_grounding_accuracy": True,
    "structured_output_validity": True,
    "abstention_recall": True,
    "inconclusive_not_accepted_rate": True,
    "false_acceptance_rate": False,
    "unsupported_acceptance_rate": False,
    "unsupported_claim_rate": False,
}


def _value(report: dict[str, Any], name: str) -> float | None:
    metric = report["metrics"].get(name)
    return metric.get("value") if isinstance(metric, dict) else None


def _cost(report: dict[str, Any]) -> dict[str, Any]:
    m = report["metrics"]
    cases = max(m["cases"] - len(m.get("cases_not_evaluated") or []), 1)
    tokens = m.get("tokens") or {}
    total = (tokens.get("input") or 0) + (tokens.get("output") or 0)
    return {
        "avg_attempts": m.get("avg_attempts"),
        "llm_latency_mean_ms": (m.get("llm_latency_ms") or {}).get("mean"),
        "llm_latency_p95_ms": (m.get("llm_latency_ms") or {}).get("p95"),
        "tokens_per_case": round(total / cases) if total else None,
        "evaluated_cases": cases,
    }


def regressions(baseline: dict[str, Any], candidate: dict[str, Any], tolerance: float) -> list[str]:
    found = []
    for name, higher_is_better in QUALITY_METRICS.items():
        before, after = _value(baseline, name), _value(candidate, name)
        if before is None or after is None:
            continue
        delta = after - before if higher_is_better else before - after
        if delta < -tolerance:
            found.append(f"{name}: {before:.3f} -> {after:.3f}")
    return found


def table(reports: list[dict[str, Any]], labels: list[str]) -> str:
    def fmt(value: Any) -> str:
        if value is None:
            return "n/a"
        return f"{value:.3f}" if isinstance(value, float) and value <= 1.0 else str(value)

    header = "| metric | " + " | ".join(labels) + " |\n|---|" + "---|" * len(labels)
    rows = [f"| {name} | " + " | ".join(fmt(_value(r, name)) for r in reports) + " |" for name in QUALITY_METRICS]
    costs = [_cost(r) for r in reports]
    rows += [f"| {key} | " + " | ".join(fmt(c[key]) for c in costs) + " |" for key in costs[0]]
    rows += [
        "| brier (model confidence) | "
        + " | ".join(
            fmt((r["metrics"].get("calibration") or {}).get("model_confidence", {}).get("brier")) for r in reports
        )
        + " |"
    ]
    return header + "\n" + "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("reports", nargs="+", type=pathlib.Path)
    parser.add_argument("--fail-on-regression", action="store_true")
    parser.add_argument("--tolerance", type=float, default=0.0)
    args = parser.parse_args(argv)
    if len(args.reports) < 2:
        parser.error("need a baseline and at least one candidate")
    reports = [json.loads(p.read_text(encoding="utf-8")) for p in args.reports]
    if len({r["dataset_version"] for r in reports}) != 1:
        print("refusing to compare reports from different datasets", file=sys.stderr)
        return 2
    labels = [
        f"{'mock' if r.get('mode') == 'mock' else r['run_metadata'].get('model', '?')} / "
        f"{r['run_metadata'].get('prompt_version', '?')}"
        for r in reports
    ]
    print(table(reports, labels))
    failures = [
        f"{label}: {item}"
        for r, label in zip(reports[1:], labels[1:], strict=True)
        for item in regressions(reports[0], r, args.tolerance)
    ]
    for failure in failures:
        print("REGRESSION", failure, file=sys.stderr)
    return 1 if failures and args.fail_on_regression else 0


if __name__ == "__main__":
    raise SystemExit(main())
