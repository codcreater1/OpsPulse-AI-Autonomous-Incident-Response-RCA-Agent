# ADR 0003 - Lexical historical retrieval before embeddings

- Status: accepted
- Date: 2026-10-09

## Context

Similar past incidents help the model, but retrieval must not leak one repository's incidents into another's
prompt, must explain why something matched, and must stay testable. Vector search (pgvector + an embedding
model) is a common default.

## Decision

Candidates are the newest 200 accepted incidents of the same repository (SQL filter). `lexical-v1` ranks them by
failure fingerprint, file, exception type and identifier-term overlap, collapses duplicate deliveries, drops
weak matches and returns at most five with reasons. The previous strategy is kept for comparison, and both are
measured on `evals/datasets/retrieval_cases.json` (recall@3 0.463 -> 0.926, MRR 0.556 -> 1.0, zero
cross-repository leaks).

## Consequences

- No extra infrastructure, no stack traces sent to an embedding provider, deterministic tests.
- The labelled dataset was written by the same author as the ranker, so the comparison is optimistic.
- Synonymous failures with no shared vocabulary will be missed. Embeddings should be evaluated against the same
  dataset (extended with real-world cases) before adoption; PostgreSQL full-text search is the next step if the
  200-row candidate window becomes the bottleneck.
