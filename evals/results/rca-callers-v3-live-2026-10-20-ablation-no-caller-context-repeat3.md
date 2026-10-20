# RCA evaluation - live mode

- Run at: 2026-10-20T18:48:13.679780+00:00  |  dataset: rca-callers-v3 (15 cases)
- Versions: {"agent_version": "1.4.0-opspulse", "prompt_version": "rca-prompt-v6.1", "evaluator_version": "quality-gate-v8", "retrieval_strategy": "lexical-v1", "model": "openai/gpt-oss-120b", "quality_threshold": 0.85, "max_analysis_iterations": 3, "max_output_tokens": 4096}

| Metric | Value | n/d | Definition |
|---|---|---|---|
| structured_output_validity | 1.000 | 13/13 | LLM attempts whose reply validated against RCAOutput / LLM attempts (provider errors excluded) |
| category_accuracy | 1.000 | 13/13 | final category == labelled category (or an accepted alternative) / cases labelled conclusive |
| evidence_grounding_accuracy | 1.000 | 28/28 | 'observed' quotes found verbatim in their cited source / all 'observed' quotes (final analyses) |
| unsupported_claim_rate | 0.000 | 0/44 | (unverifiable 'observed' quotes + affected files absent from trace/retrieved file) / (all quotes + all affected files) |
| abstention_recall | n/a | 0/0 | inconclusive-labelled cases where the model declared insufficient evidence or category 'unknown' / inconclusive-labelled cases |
| inconclusive_not_accepted_rate | n/a | 0/0 | inconclusive-labelled cases the quality gate did NOT accept / inconclusive-labelled cases |
| false_abstention_rate | 0.000 | 0/13 | conclusive-labelled cases where the model abstained / conclusive-labelled cases |
| gate_acceptance_rate | 0.231 | 3/13 | cases accepted by the quality gate / evaluated cases |
| false_acceptance_rate | 0.000 | 0/3 | accepted cases that are inconclusive-labelled or have the wrong category / accepted cases |
| relevant_file_hit_rate | 1.000 | 13/13 | cases whose affected_files contain a labelled relevant file / cases with labelled files |
| unsupported_acceptance_rate | n/a | 0/0 | unsupported analyses (inconclusive-labelled or with an unverifiable quote) the gate accepted / unsupported analyses |
| workflow_failure_rate | 0.133 | 2/15 | cases ending in workflow status 'failed' (e.g. provider errors) / cases |

- Average attempts: 1.0
- Not evaluated (provider prevented completion): ['caller-empty-list', 'caller-two-levels-up']
- LLM latency ms: {'mean': 9818, 'p95': 24817, 'samples': 13}  |  case wall ms: {'mean': 9415, 'p95': 24821}
- Tokens: {'input': 28283, 'output': 19929, 'attempts_with_usage': 13}  |  estimated cost USD: None

| Case | Expected | Predicted | Gate | Status | Attempts | Quotes ok |
|---|---|---|---|---|---|---|
| caller-passes-none | null_reference | null_reference | fail | needs_review | 1 | 2/2 |
| caller-passes-none | null_reference | null_reference | fail | needs_review | 1 | 2/2 |
| caller-passes-none | null_reference | null_reference | fail | needs_review | 1 | 2/2 |
| caller-empty-list | logic_error | logic_error | fail | needs_review | 1 | 2/2 |
| caller-empty-list | logic_error | logic_error | fail | needs_review | 1 | 3/3 |
| caller-empty-list | logic_error | None | fail | failed | 1 | 0/0 |
| caller-symptomatic-patch | null_reference | null_reference | fail | needs_review | 1 | 2/2 |
| caller-symptomatic-patch | null_reference | null_reference | fail | needs_review | 1 | 2/2 |
| caller-symptomatic-patch | null_reference | null_reference | fail | needs_review | 1 | 2/2 |
| caller-two-levels-up | type_error | type_error | fail | needs_review | 1 | 2/2 |
| caller-two-levels-up | type_error | type_error | fail | needs_review | 1 | 2/2 |
| caller-two-levels-up | type_error | None | fail | failed | 1 | 0/0 |
| control-cause-in-trigger | logic_error | logic_error | pass | accepted | 1 | 2/2 |
| control-cause-in-trigger | logic_error | logic_error | pass | accepted | 1 | 3/3 |
| control-cause-in-trigger | logic_error | logic_error | pass | accepted | 1 | 2/2 |

### Run-to-run consistency (5 repeated case(s); stable outcome 5/5)

| Case | Runs | Accepted | Correct category | Distinct outcomes |
|---|---|---|---|---|
| caller-passes-none | 3 | 0 | 3 | 1 |
| caller-empty-list | 2 | 0 | 2 | 1 |
| caller-symptomatic-patch | 3 | 0 | 3 | 1 |
| caller-two-levels-up | 2 | 0 | 2 | 1 |
| control-cause-in-trigger | 3 | 3 | 3 | 1 |
