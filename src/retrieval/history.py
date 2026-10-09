"""Ranking of historical incidents. Pure functions: the database query only supplies candidates.

Two strategies are kept side by side so they can be compared on the same labelled dataset
(`python -m evals.run_retrieval`):

- ``fingerprint-or-file-v0`` - the original behaviour: exact failure fingerprint or same file, newest first.
- ``lexical-v1`` - adds exception-type and term-overlap evidence, deduplicates repeated failures, drops
  weak matches and explains every match.

Neither is semantic search: both are keyword/structure based. See README "Retrieval".
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from src.agent.parsing import extract_exception_type, extract_frames, normalize_path

MAX_QUERY_CHARS = 8_000  # very large inputs are truncated before tokenisation
MIN_SCORE = 1.2
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_STOPWORDS = frozenset(
    [
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "not",
        "none",
        "true",
        "false",
        "self",
        "traceback",
        "most",
        "recent",
        "call",
        "last",
        "file",
        "line",
        "error",
        "exception",
        "raise",
        "return",
        "in",
        "at",
        "of",
        "to",
        "is",
        "was",
    ]
)


@dataclass(frozen=True)
class HistoryQuery:
    repo_name: str
    fingerprint: str
    error_message: str
    stack_trace: str
    affected_file: str | None


@dataclass(frozen=True)
class HistoryCandidate:
    id: str
    repo_name: str
    fingerprint: str
    error_message: str
    stack_trace: str
    affected_file: str | None
    extra: dict[str, Any]  # fields passed through to the prompt (summary, past patch, status, ...)


@dataclass(frozen=True)
class RankedIncident:
    candidate: HistoryCandidate
    score: float
    reasons: tuple[str, ...]


def tokenize(text: str) -> set[str]:
    words = _TOKEN_RE.findall((text or "")[:MAX_QUERY_CHARS].lower())
    return {w for w in words if w not in _STOPWORDS}


def _terms(error_message: str, stack_trace: str, affected_file: str | None) -> set[str]:
    frames, _ = extract_frames((stack_trace or "")[:MAX_QUERY_CHARS])
    functions = " ".join(f.function for f in frames)
    file_part = normalize_path(affected_file).replace("/", " ").replace(".", " ") if affected_file else ""
    return tokenize(f"{error_message} {functions} {file_part}")


def _score_lexical(query: HistoryQuery, cand: HistoryCandidate) -> tuple[float, tuple[str, ...]]:
    score, reasons = 0.0, []
    if cand.fingerprint == query.fingerprint:
        score += 3.0
        reasons.append("same failure fingerprint")
    if query.affected_file and cand.affected_file == query.affected_file:
        score += 1.5
        reasons.append(f"same file {cand.affected_file}")
    q_exc = extract_exception_type(query.error_message, query.stack_trace)
    if q_exc != "UnknownError" and q_exc == extract_exception_type(cand.error_message, cand.stack_trace):
        score += 1.0
        reasons.append(f"same exception type {q_exc}")
    q_terms = _terms(query.error_message, query.stack_trace, query.affected_file)
    c_terms = _terms(cand.error_message, cand.stack_trace, cand.affected_file)
    shared = q_terms & c_terms
    if shared:
        score += 2.0 * len(shared) / len(q_terms | c_terms)
        reasons.append("shared terms: " + ", ".join(sorted(shared)[:6]))
    return round(score, 4), tuple(reasons)


def _score_v0(query: HistoryQuery, cand: HistoryCandidate) -> tuple[float, tuple[str, ...]]:
    if cand.fingerprint == query.fingerprint:
        return 2.0, ("same failure fingerprint",)
    if query.affected_file and cand.affected_file == query.affected_file:
        return 1.0, (f"same file {cand.affected_file}",)
    return 0.0, ()


def rank_lexical(query: HistoryQuery, candidates: Sequence[HistoryCandidate], k: int = 5) -> list[RankedIncident]:
    """Candidates must be ordered newest first. Returns at most k matches scoring >= MIN_SCORE."""
    if not (query.error_message.strip() or query.stack_trace.strip()):
        return []
    seen: set[str] = set()
    ranked: list[tuple[int, RankedIncident]] = []
    for position, cand in enumerate(candidates):
        if cand.repo_name != query.repo_name:  # defence in depth: the SQL query already filters by repository
            continue
        if cand.fingerprint in seen:  # repeated deliveries of the same failure: keep the newest only
            continue
        seen.add(cand.fingerprint)
        score, reasons = _score_lexical(query, cand)
        if score >= MIN_SCORE:
            ranked.append((position, RankedIncident(cand, score, reasons)))
    ranked.sort(key=lambda item: (-item[1].score, item[0]))
    return [r for _, r in ranked[:k]]


def rank_fingerprint_or_file(
    query: HistoryQuery, candidates: Sequence[HistoryCandidate], k: int = 5
) -> list[RankedIncident]:
    """Original v0 behaviour (kept for comparison): fingerprint matches first, then same file, newest first."""
    ranked = []
    for position, cand in enumerate(candidates):
        if cand.repo_name != query.repo_name:
            continue
        score, reasons = _score_v0(query, cand)
        if score > 0:
            ranked.append((position, RankedIncident(cand, score, reasons)))
    ranked.sort(key=lambda item: (-item[1].score, item[0]))
    return [r for _, r in ranked[:k]]


def to_prompt_records(ranked: Sequence[RankedIncident]) -> list[dict[str, Any]]:
    """Shape ranked matches for the prompt / graph state, including why each one matched."""
    return [
        {
            "id": r.candidate.id,
            "score": r.score,
            "match_reasons": list(r.reasons),
            "error_message": r.candidate.error_message[:500],
            "affected_file": r.candidate.affected_file,
            **r.candidate.extra,
        }
        for r in ranked
    ]


Ranker = Callable[[HistoryQuery, Sequence[HistoryCandidate], int], list[RankedIncident]]
STRATEGIES: dict[str, Ranker] = {
    "fingerprint-or-file-v0": rank_fingerprint_or_file,
    "lexical-v1": rank_lexical,
}
