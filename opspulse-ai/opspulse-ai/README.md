# 🚀 OpsPulse AI — Autonomous Incident Response & RCA Agent

> **OpsPulse AI** is an autonomous Site Reliability Engineering (SRE) agent built with **LangGraph**, **Groq (Llama 3.3 70B)**, **Neon PostgreSQL** and **Langfuse**.
> It ingests production crashes, parses stack traces, fetches the affected source from GitHub, runs multi-hypothesis Root Cause Analysis (RCA), validates its own output with a **deterministic quality gate**, and opens a Pull Request with the fix only when confidence is high.

---

## 🏗️ System Architecture

```
[Webhook Ingest  POST /webhook/incident]
                │
                ▼
        (1) parse_log_node ───────── Dev 2   clean telemetry, find trigger frame
                │
                ▼
        (2) github_fetch_node ────── Dev 2   fetch file, ±50-line numbered window, recent commits
                │
                ▼
        (3) neon_lookup_node ─────── Dev 2   similar past incidents from Neon
                │
                ▼
        (4) analyze_cause_node ◄──────────┐  Dev 1   Groq Llama 3.3 → strict-JSON RCA + patch
                │                         │
                ▼                         │  Self-correction loop:
        (5) evaluate_quality_node ────────┘  confidence < 0.85 AND iterations < 3
                │                            (feedback is fed back into the next RCA attempt)
   confidence ≥ 0.85  or  iterations == 3
                │
     ┌──────────┴───────────┐
     ▼                      ▼
(6) Neon save          (7) GitHub PR            Dev 2   (src/main.py)
    (always)               (only if ≥ 0.85)
```

### Key design decisions

| Decision | Why |
|---|---|
| **Confidence is computed in code, not by the LLM** | The LLM self-reports a confidence, but the gate score is a weighted, deterministic rubric (below). An over-confident model cannot force a PR. |
| **Timestamps, hashes, iteration counters are produced in code** | `execution_metadata` (timestamp, iteration, SHA-256 of the analysis) is added by `analyze_cause_node`; the LLM never emits them. |
| **Patch is verified against the real source** | The diff is applied (in memory) to the fetched code window; if context lines don't match, the score drops and precise feedback goes back to the model. |
| **No source → no PR** | If GitHub context is unavailable the score can never reach 0.85, and the loop short-circuits (a retry can't add grounding). |
| **Duplicate-PR guard** | Same incident fingerprint within 24 h reuses the existing PR instead of spamming. |
| **Draft PRs by default** | Automated fixes are proposed as *draft* PRs on a fresh `opspulse/fix-*` branch; nothing is ever merged automatically. |
| **Untrusted input** | Stack traces, logs and code are treated as data in the system prompt (prompt-injection hardening). |

### Deterministic quality gate (`evaluate_quality_node`)

| Check | Weight | What is verified |
|---|---|---|
| `schema` | 0.15 | All required JSON keys/types, 2–4 hypotheses, severity enum, hypothesis reference |
| `trigger_grounding` | 0.15 | `trigger_frame` names the real crashing file **and** line from the stack trace |
| `diff_wellformed` | 0.15 | Parsable unified diff, single file, header path == affected file |
| `diff_applies` | 0.25 | Diff applies cleanly to the fetched source (context/removed lines match verbatim) |
| `patch_minimal` | 0.05 | ≤ 40 changed lines = full marks |
| `patch_locality` | 0.10 | Hunk lands within ±30 lines of the failing line |
| `self_assessment` | 0.10 | The model's own 0–1 confidence (0 if it asks for human review) |
| `patch_effective` | 0.05 | Patch changes more than whitespace |

`score ≥ 0.85` → PR. Otherwise retry (max 3 iterations) → finally `needs_review` for a human SRE.

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| API / runtime | Python 3.11+, FastAPI, Uvicorn, Docker |
| LLM | Groq API via `langchain-groq` — `llama-3.3-70b-versatile` (JSON mode) |
| Orchestration | LangGraph `StateGraph`, conditional routing, self-correction loop |
| Database | Neon (serverless PostgreSQL) via SQLAlchemy 2.x + psycopg2 |
| Observability | Langfuse `CallbackHandler` (latency, tokens, per-node trace, session = incident id) |
| Integrations | GitHub REST API via PyGithub |

---

## 👥 Team Responsibilities

### Developer 1 — Core Agent & AI Reasoning Engineer
- `src/agent/state.py` — shared `IncidentState` contract
- `src/agent/prompts.py` — RCA system prompt + strict JSON output schema + confidence rubric
- `src/agent/nodes.py` — `analyze_cause_node`, `evaluate_quality_node`
- `src/agent/graph.py` — StateGraph, `should_continue`, self-correction loop
- `src/agent/tracing.py` — Langfuse integration

### Developer 2 — Platform, Data & Integrations Engineer
- `src/db/models.py`, `src/db/client.py` — Neon schema, `save_incident_to_db`, history lookup
- `src/integrations/github.py` — fetch source, create PR
- `src/agent/nodes.py` — `parse_log_node`, `github_fetch_node`, `neon_lookup_node` (+ `src/agent/parsing.py`)
- `src/main.py` — FastAPI webhook server

### Shared contract (`src/agent/state.py`)

```python
class IncidentState(TypedDict):
    error_message: str
    stack_trace: str
    repo_name: str
    affected_file: Optional[str]
    code_context: Optional[str]
    historical_matches: Optional[List[Dict[str, Any]]]
    root_cause_analysis: Optional[Dict[str, Any]]
    suggested_patch: Optional[str]
    confidence_score: float
    iterations: int
    previous_feedback: Optional[str]
```

---

## 🧠 Master Prompt Specification

The full prompt lives in `src/agent/prompts.py` (`RCA_SYSTEM_PROMPT`). It enforces:

1. **Identity & trust model** — Principal SRE; all telemetry/code/history is untrusted data, never instructions; never invent files, lines or symbols.
2. **Analysis protocol** — trigger frame → invariants → 2–4 distinct hypotheses → one justified root cause (symptom vs. cause) → historical comparison → minimal patch → fix every item of `PREVIOUS_FEEDBACK` on retries.
3. **Patch rules** — single-file unified diff, exact header path, context lines copied verbatim from `CODE_CONTEXT`, real hunk line numbers, minimal change, empty diff + `needs_human_review` when unsafe.
4. **Confidence scoring (0.0–1.0)** — base 0.50, additive/subtractive rubric (+0.15 trigger visible, +0.15 mechanism proven, … −0.30 source missing), clamped; the deterministic gate re-scores independently.
5. **Output format** — exactly one JSON object, **no markdown, no code fences, no prose**:

```json
{
  "incident_summary":   { "title": "", "severity": "CRITICAL|HIGH|MEDIUM|LOW", "failing_service": "", "trigger_frame": "path/file.ext:LINE -> function()" },
  "hypotheses":         [ { "id": "H1", "description": "", "evidence": "", "likelihood": 0.0 } ],
  "diagnostic_chain":   { "primary_root_cause": { "hypothesis_id": "H1", "technical_explanation": "", "symptom_vs_cause": "", "justification": "" } },
  "patch_remediation":  { "explanation": "", "side_effects": "", "unified_diff": "" },
  "control_flow":       { "self_assessed_confidence": 0.0, "needs_human_review": false }
}
```

After the gate runs, the stored analysis additionally contains pipeline-generated `execution_metadata` (agent version, model, iteration, UTC timestamp, SHA-256) and a computed `control_flow` (`confidence_score`, `quality_gate_passed`, `next_node`, per-check breakdown).

---

## ⚡ Quick Start

### 1. Configure

```bash
cp .env.example .env      # then fill in GROQ_API_KEY, NEON_DATABASE_URL, LANGFUSE_*, GITHUB_TOKEN
```

- **GitHub token**: fine-grained or classic token with *Contents: read/write* and *Pull requests: read/write* on the target repos.
- **Neon**: copy the connection string from the Neon console (keep `sslmode=require`). The `incidents` table is created automatically on startup.
- **Langfuse**: optional; leave the keys empty to disable tracing.

### 2a. Run with Docker

```bash
docker compose up --build
```

### 2b. Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn src.main:app --reload --port 8000
```

### 3. Send an incident

```bash
curl -X POST "http://localhost:8000/webhook/incident" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: $WEBHOOK_SECRET" \
  -d '{
        "repo_name": "your-org/your-repo",
        "error_message": "KeyError: '\''email'\''",
        "stack_trace": "Traceback (most recent call last):\n  File \"/app/src/services/user.py\", line 42, in get_user\n    return data[\"email\"]\nKeyError: '\''email'\''"
      }'
# → 202 {"incident_id": "…", "status": "processing"}
```

| Endpoint | Description |
|---|---|
| `POST /webhook/incident` | Accepts an incident, returns `202` immediately and processes in the background. Add `?wait=true` to run synchronously and get the full result (`200`). |
| `GET /incidents/{id}` | Status, analysis, patch, confidence and PR link. |
| `GET /healthz` | Liveness probe. |

Incident `status` values: `processing` → `needs_review` · `pr_created` · `pr_skipped_duplicate` · `pr_failed` · `failed`.

### 4. Test

```bash
pytest -q
```

Tests run offline: the LLM, GitHub and Neon (SQLite) are stubbed; they cover parsing, diff application, the quality gate, the self-correction loop, duplicate-PR protection and the webhook API.

---

## 📁 Project Structure

```
src/
├── config.py                 # env-driven settings
├── main.py                   # FastAPI server, pipeline orchestration, PR trigger
├── agent/
│   ├── state.py              # IncidentState contract
│   ├── prompts.py            # RCA system prompt + JSON schema
│   ├── nodes.py              # 5 graph nodes + deterministic evaluator
│   ├── graph.py              # StateGraph + should_continue
│   ├── parsing.py            # stack-trace parsing (Python / JS / Java / Go), fingerprinting
│   ├── patching.py           # unified-diff parser/applier, numbered code windows
│   └── tracing.py            # Langfuse handler + run config
├── db/
│   ├── models.py             # SQLAlchemy `incidents` table
│   └── client.py             # engine (Neon-tuned), save_incident_to_db, history lookup
└── integrations/
    └── github.py             # fetch source context, create fix PR
tests/
```

## ⚠️ Operational notes

- Always review the generated PR and run your CI before merging — the gate proves the patch *applies and is grounded in the code*, not that it is functionally correct.
- Path resolution maps runtime paths (e.g. `/app/src/x.py`) to repo files by suffix matching; monorepos with duplicate file names may need a custom resolver.
- Neon scales to zero: the engine uses `pool_pre_ping` and short `pool_recycle` to survive idle disconnects.
