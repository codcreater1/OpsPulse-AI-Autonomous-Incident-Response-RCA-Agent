"""Prometheus metrics (exposed at GET /metrics when METRICS_ENABLED=true).

Labels are deliberately low-cardinality and content-free: statuses, categories and outcomes only - no repository
names, identities, file paths or error text.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import Counter, Gauge, Histogram

INCIDENTS = Counter(
    "opspulse_incidents_finished_total", "Incidents that reached a final status", ["status", "error_category"]
)
PIPELINE_SECONDS = Histogram(
    "opspulse_pipeline_duration_seconds",
    "Wall time of one incident pipeline run (graph + persistence + remediation)",
    buckets=(1, 2.5, 5, 10, 20, 40, 80, 160, 320),
)
LLM_ATTEMPTS = Counter("opspulse_llm_attempts_total", "LLM analysis attempts by outcome", ["outcome"])
LLM_SECONDS = Histogram(
    "opspulse_llm_call_duration_seconds", "Latency of one LLM call", buckets=(0.5, 1, 2, 4, 8, 16, 32, 64)
)
LLM_TOKENS = Counter("opspulse_llm_tokens_total", "Provider-reported tokens", ["direction"])
QUALITY_GATE = Counter("opspulse_quality_gate_evaluations_total", "Quality-gate decisions", ["result"])
QUEUE_DEPTH = Gauge("opspulse_queue_depth", "Incidents waiting in the queue (sampled by the worker)")
JOBS_RECOVERED = Counter("opspulse_jobs_recovered_total", "Expired worker claims", ["outcome"])
JOBS_DEFERRED = Counter(
    "opspulse_jobs_deferred_total", "Incidents re-queued with backoff after a transient error", ["error_category"]
)
NOTIFICATIONS = Counter("opspulse_notifications_total", "Reviewer notifications", ["outcome"])
DECISIONS = Counter("opspulse_remediation_decisions_total", "Human remediation decisions", ["decision"])


def record_attempt(attempt: dict[str, Any]) -> None:
    if "error_category" in attempt:
        outcome = "provider_error"
    elif not attempt.get("valid_json"):
        outcome = "malformed"
    elif not attempt.get("schema_valid"):
        outcome = "schema_invalid"
    else:
        outcome = "valid"
    LLM_ATTEMPTS.labels(outcome).inc()
    if attempt.get("latency_ms") is not None:
        LLM_SECONDS.observe(attempt["latency_ms"] / 1000)
    for direction in ("input", "output"):
        if attempt.get(f"{direction}_tokens"):
            LLM_TOKENS.labels(direction).inc(attempt[f"{direction}_tokens"])


def record_gate(passed: bool) -> None:
    QUALITY_GATE.labels("passed" if passed else "rejected").inc()


def record_incident(status: str, error_category: str | None) -> None:
    INCIDENTS.labels(status, error_category or "none").inc()


def record_decision(approved: bool) -> None:
    DECISIONS.labels("approved" if approved else "rejected").inc()
