"""Merge partial evaluation reports of the SAME configuration into one report.

    python -m evals.merge_reports first.json second.json -o merged.json

Used when a live run was cut short (e.g. provider quota) and the missing cases were run later. Refuses to merge
reports whose dataset or run metadata (model, prompt, evaluator, retrieval versions, thresholds) differ. For each
case the last report in which it was actually evaluated wins; the merged report lists its source runs.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from datetime import UTC, datetime
from typing import Any

from evals.metrics import _provider_failed, compute_metrics
from evals.run_rca import _summary


class IncompatibleReportsError(ValueError):
    pass


def merge(reports: list[dict[str, Any]]) -> dict[str, Any]:
    if len(reports) < 2:
        raise IncompatibleReportsError("need at least two reports")
    first = reports[0]
    for other in reports[1:]:
        for key in ("mode", "dataset_version", "run_metadata"):
            if other.get(key) != first.get(key):
                raise IncompatibleReportsError(f"reports differ in {key}; refusing to merge")
    by_case: dict[str, dict[str, Any]] = {}
    for report in reports:
        for result in report["results"]:
            previous = by_case.get(result["case_id"])
            if previous is None or _provider_failed(previous) or not _provider_failed(result):
                by_case[result["case_id"]] = result
    results = list(by_case.values())
    return {
        **{k: first[k] for k in ("mode", "dataset_version", "run_metadata")},
        "started_at": min(r["started_at"] for r in reports),
        "merged_at": datetime.now(UTC).isoformat(),
        "merged_from": [r["started_at"] for r in reports],
        "metrics": compute_metrics(results),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("reports", nargs="+", type=pathlib.Path)
    parser.add_argument("-o", "--out", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    merged = merge([json.loads(p.read_text(encoding="utf-8")) for p in args.reports])
    args.out.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    summary = _summary(merged) + f"\nMerged from runs started at: {', '.join(merged['merged_from'])}\n"
    args.out.with_suffix(".md").write_text(summary, encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
