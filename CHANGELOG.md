# Changelog

All notable changes are listed here. Versions of behaviour-critical components are tracked separately in
`src/versions.py` (prompt, quality gate, retrieval strategy).

## [Unreleased]

### Added
- Sentry webhook adapter (`POST /integrations/sentry`): HMAC signature verification, project-to-repository
  mapping, idempotent per Sentry event, size and rate limits.
- Durable PostgreSQL-backed job queue (migration 0004): compare-and-set claims with leases, automatic
  re-queueing of crashed workers' incidents, `python -m src.worker`, Compose `worker` service, queue metrics.
  Replaces FastAPI BackgroundTasks and the startup "mark interrupted" sweep.
- Review console at `/console` (strict CSP, textContent-only rendering) and `scripts/seed_demo_data.py`;
  baseline security headers on every response.
- Role-based API keys (`API_KEYS=name:role:sha256`; reporter / reviewer / admin) and `scripts/make_api_key.py`.
- Four-eyes rule: the identity that submitted an incident cannot decide its remediation; the approver is the
  authenticated identity (no longer a self-declared name).
- Per-identity rate limiting for incident submission (429 with `Retry-After`).
- Recovery of incidents left in `processing` by a crashed process (`error_category=interrupted`).
- Alembic migration 0003 (`incidents.submitted_by`).
- `GET /incidents` with status/repository filters and keyset pagination.
- Prometheus `/metrics` (incident outcomes, LLM attempts/latency/tokens, gate decisions, approvals).
- CI job running migrations (round trip + `alembic check`) and the unit tests on PostgreSQL 16.
- MIT license, security policy, contributing guide, ADRs, pre-commit hooks, Dependabot.

### Fixed
- CI: restored the `langchain` dependency required by Langfuse's LangChain handler; the handler is now imported
  lazily so a missing tracing integration cannot prevent startup.

## [1.1.0] - 2026-10-09

### Added
- Evidence-labelled structured RCA (Pydantic), deterministic quality gate with blocking checks and verbatim
  quote verification, bounded self-correction with evaluator feedback.
- Human approval bound to the patch SHA-256 before any GitHub write; deterministic remediation branches;
  duplicate-PR guard; patch policy (single file, no `.github/`, size limit).
- Failure taxonomy, Alembic migrations 0001-0002, prompt/model/evaluator/retrieval versioning.
- Lexical-v1 historical retrieval with repository isolation and match explanations.
- Langfuse v4 tracing with content masking; structured JSON logs with secret redaction.
- Evaluation framework (26-case RCA dataset, retrieval dataset, mock/live runners), sandboxed demo,
  GitHub Actions CI, Docker setup.

### Fixed
- Wrong trigger frames could pass the gate; multi-file diffs could be parsed as single-file; the prompt's
  example diff taught literal `\n` escapes; webhook auth failed open when no secret was set.
