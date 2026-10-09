"""Compare historical-incident ranking strategies on the labelled retrieval dataset.

    python -m evals.run_retrieval [--k 3]

Metrics (macro-averaged over queries; see README "Retrieval evaluation"):
- recall@k     |relevant ∩ top-k| / |relevant|                      queries with >= 1 relevant incident
- precision    |relevant ∩ returned| / |returned|                  queries that returned >= 1 result
- mrr          1 / rank of the first relevant result (0 if none)    queries with >= 1 relevant incident
- empty_ok     returned nothing                                     queries with no relevant incident
- leaks        results from another repository                       all queries (must be 0)
- duplicates   results sharing a failure fingerprint                 all queries
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
from datetime import UTC, datetime
from typing import Any

os.environ.setdefault("DATABASE_URL", "sqlite://")

from src.agent.parsing import compute_fingerprint
from src.retrieval.history import STRATEGIES, HistoryCandidate, HistoryQuery

DATASET = pathlib.Path(__file__).parent / "datasets" / "retrieval_cases.json"
REPORTS = pathlib.Path(__file__).with_name("reports")


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def evaluate_strategy(name: str, data: dict[str, Any], k: int) -> dict[str, Any]:
    ranker = STRATEGIES[name]
    by_id = {c["id"]: c for c in data["corpus"]}
    recalls, precisions, rrs, empty_ok, leaks, dupes, per_query = [], [], [], [], 0, 0, []
    for q in data["queries"]:
        # The SQL layer filters by repository; here we pass the whole corpus so the ranker's own repository
        # check is exercised too (defence in depth).
        candidates = [
            HistoryCandidate(
                c["id"],
                c["repo_name"],
                compute_fingerprint(c["repo_name"], c["error_message"], c["stack_trace"]),
                c["error_message"],
                c["stack_trace"],
                c["affected_file"],
                {},
            )
            for c in data["corpus"]
        ]
        query = HistoryQuery(
            q["repo_name"],
            compute_fingerprint(q["repo_name"], q["error_message"], q["stack_trace"]),
            q["error_message"],
            q["stack_trace"],
            q["affected_file"],
        )
        returned = [r.candidate.id for r in ranker(query, candidates, k)]
        relevant = set(q["relevant_ids"])
        leaks += sum(1 for i in returned if by_id[i]["repo_name"] != q["repo_name"])
        fps = [
            compute_fingerprint(by_id[i]["repo_name"], by_id[i]["error_message"], by_id[i]["stack_trace"])
            for i in returned
        ]
        dupes += len(fps) - len(set(fps))
        if relevant:
            recalls.append(len(relevant & set(returned[:k])) / len(relevant))
            rank = next((pos for pos, i in enumerate(returned, start=1) if i in relevant), None)
            rrs.append(1 / rank if rank else 0.0)
        else:
            empty_ok.append(1.0 if not returned else 0.0)
        if returned:
            precisions.append(len(relevant & set(returned)) / len(returned))
        per_query.append({"query": q["id"], "relevant": sorted(relevant), "returned": returned})
    return {
        f"recall@{k}": _mean(recalls),
        "precision": _mean(precisions),
        "mrr": _mean(rrs),
        "empty_ok": _mean(empty_ok),
        "leaks": leaks,
        "duplicates": dupes,
        "per_query": per_query,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--out", type=pathlib.Path, default=REPORTS)
    args = parser.parse_args(argv)
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    results = {name: evaluate_strategy(name, data, args.k) for name in STRATEGIES}
    started = datetime.now(UTC)
    report = {
        "started_at": started.isoformat(),
        "dataset_version": data["version"],
        "k": args.k,
        "queries": len(data["queries"]),
        "strategies": results,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"retrieval-{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    keys = [f"recall@{args.k}", "precision", "mrr", "empty_ok", "leaks", "duplicates"]
    print(f"Retrieval evaluation ({data['version']}, {len(data['queries'])} queries, k={args.k})\n")
    print("| strategy | " + " | ".join(keys) + " |")
    print("|" + "---|" * (len(keys) + 1))
    for name, r in results.items():
        print(f"| {name} | " + " | ".join(str(r[key]) for key in keys) + " |")
    print("\nper query (lexical-v1):")
    for row in results["lexical-v1"]["per_query"]:
        print(f"  {row['query']}: relevant={row['relevant']} returned={row['returned']}")
    print(f"\nreport: {path}")
    return 1 if any(r["leaks"] for r in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
