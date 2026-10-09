# ADR 0002 - Side effects run once, after the graph; no LangGraph checkpointer

- Status: accepted
- Date: 2026-10-09

## Context

The analysis node may run up to `MAX_ANALYSIS_ITERATIONS` times. If persistence or GitHub calls lived in graph
nodes, a retry or a resumed run could repeat them (duplicate rows, duplicate PRs). LangGraph offers
checkpointing and `interrupt()` for human-in-the-loop pauses.

## Decision

Graph nodes only read external systems and return state updates. The service layer persists the final state
and performs remediation exactly once after the graph finishes. The human approval pause happens *after* the
graph, as a row in `remediation_approvals`, decided through an API call and claimed with a compare-and-set
update before any GitHub write.

No checkpointer is used: the graph completes within one request (seconds to a minute) and everything needed to
continue later is already in PostgreSQL. A checkpointer would add a second source of truth without a measured
benefit.

## Consequences

- Retries cannot cause duplicate side effects; approval resumes survive restarts because they are plain rows.
- Since migration 0004 incidents go through a durable queue with leased claims: an analysis interrupted by a
  crash is re-queued and restarts from the beginning (bounded by `MAX_JOB_ATTEMPTS`). It does not resume
  mid-graph; a checkpointer would only save the LLM calls already made, which was not judged worth a second
  source of truth.
