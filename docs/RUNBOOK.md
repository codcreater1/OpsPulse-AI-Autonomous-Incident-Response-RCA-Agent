# OpsPulse AI runbook

Operational procedures for a deployment. Example alert rules: [`deploy/prometheus/alerts.yml`](../deploy/prometheus/alerts.yml).
All commands assume the service's environment (`DATABASE_URL` etc.) is loaded.

## Health checks

| Check | Meaning |
|---|---|
| `GET /healthz` 200 | process is up (liveness) |
| `GET /readyz` 200 | database answers (readiness); 503 means requests needing the DB will also return 503 |
| `opspulse_queue_depth` | incidents waiting for a worker |

## Queue backlog

Symptom: `opspulse_queue_depth` keeps growing; incidents stay `queued`.

1. Are workers running? With Compose: `docker compose ps worker`. Without Compose, the API runs one embedded
   worker unless `EMBEDDED_WORKER=false`.
2. Are they failing? Look for `worker iteration failed` or `database unavailable` in the JSON logs.
3. Scale out: `docker compose up -d --scale worker=3` (claims are safe with any number of workers).
4. If the LLM provider is the bottleneck (rate limits), more workers make it worse - see the next section.

## LLM provider errors

Symptom: incidents end as `failed` with `error_category` `llm_rate_limited`, `llm_auth`, `llm_unavailable` or
`llm_timeout`; `opspulse_llm_attempts_total{outcome="provider_error"}` rises.

- `llm_auth`: the Groq key is invalid or revoked - rotate `GROQ_API_KEY` and restart.
- `llm_unavailable` with `model_unavailable` in the reason: the model was retired - set `MODEL_NAME`, run
  `python -m evals.run_rca --mode live` against the new model **before** switching production, bump nothing
  else.
- `llm_rate_limited`, `llm_timeout`, `llm_unavailable` are transient: the incident is re-queued with backoff
  (watch `opspulse_jobs_deferred_total`) and fails only after `MAX_TRANSIENT_RETRIES` claims. If the quota is
  exhausted for longer (e.g. a daily token limit), reduce worker count or upgrade the tier, then re-queue the
  failed incidents with `POST /incidents/{id}/retry` (or the console's *Retry* button).

## Model output quality

Symptom: rising `malformed` / `schema_invalid` attempts or falling gate acceptance.

1. Run `python -m evals.run_rca --mode live` and compare with the last report (`evals/reports/`).
2. If a prompt change caused it, revert and bump `PROMPT_VERSION` only with a passing evaluation.

## Interrupted incidents

A worker that dies leaves its incident `processing`; when the lease (`JOB_LEASE_SECONDS`) expires another worker
re-queues it. After `MAX_JOB_ATTEMPTS` claims it becomes `failed / interrupted`. Repeated interruptions usually
mean the container is OOM-killed or restarted mid-analysis - check container exits and memory limits.
To retry an interrupted incident, use `POST /incidents/{id}/retry` (reviewer or admin) or the console.

## PR creation fails

Symptom: approved incidents end as `pr_failed`.

- `github_permission`: the token cannot read or write the repository. Fine-grained token needs *Contents* and
  *Pull requests* read & write on the allow-listed repositories.
- `github_rate_limited`: wait; PR creation is not retried automatically.
- "branch ... already exists": a branch `opspulse/fix-<fingerprint>` from an earlier attempt or closed PR
  exists. Delete it (or enable automatic head-branch deletion) and ask the reviewer to re-submit.
- "patch does not apply to the default branch head": the code changed since the analysis; re-submit the
  incident so the analysis runs against current code.

## Rotating API keys

1. `python -m scripts.make_api_key <name> <role>` for the replacement key.
2. Add the new entry to `API_KEYS` **next to** the old one (names must differ, e.g. `alice-2026q4`), deploy.
3. Hand the new key over, remove the old entry, deploy again.

Keys are stored only as SHA-256 digests; a leaked configuration file does not reveal usable keys.

## Rotating the Sentry client secret

Regenerate it in the Sentry integration, update `SENTRY_CLIENT_SECRET`, deploy. Webhooks signed with the old
secret are rejected with 401 in between; Sentry's delivery log shows them.

## Database migrations

- Deploys run `alembic upgrade head` before serving (Docker `CMD`). A failed migration stops the container.
- Check the revision: `alembic current`. Roll back one step: `alembic downgrade -1` (every revision has a
  downgrade; CI runs an upgrade/downgrade/upgrade round trip on PostgreSQL).
- Databases created before Alembic was introduced: `alembic stamp 0001`, then `alembic upgrade head`.

## Disabling remediation quickly

Set `ENABLE_GITHUB_REMEDIATION=false` and restart. Pending approvals stay pending; approving one then re-checks
the configuration and ends as `analysis_ready` without touching GitHub.
