# ADR 0001 - A deterministic quality gate instead of an LLM judge

- Status: accepted
- Date: 2026-10-09

## Context

Each analysis attempt must be accepted, retried with feedback, or sent to a human. An LLM-as-judge is the
obvious option, but it shares the generator's failure modes (it can be persuaded by confident prose or by
injected text), costs another call per attempt, and produces scores that drift between model versions.

## Decision

Acceptance is decided by pure functions in `src/agent/evaluation.py`: schema validity, trigger-frame grounding,
**verbatim verification of every "observed" evidence quote against the source it cites**, file grounding,
mechanical patch applicability to the retrieved code, locality and size. Some checks are *blocking*; the total
must also reach `QUALITY_THRESHOLD`. The model's self-reported confidence has a small weight and cannot pass the
gate on its own.

## Consequences

- Deterministic, cheap, unit-testable; an over-confident or injection-compliant reply cannot force acceptance.
- The gate measures grounding and applicability, **not correctness**: a well-grounded but wrong diagnosis is
  accepted (measured: 1 of 17 accepted cases in the mock evaluation). Human review stays mandatory.
- Analyses whose correct conclusion is "no code change" can never pass; since `quality-gate-v3` they stop with
  `no_code_fix` instead of burning the retry budget.
