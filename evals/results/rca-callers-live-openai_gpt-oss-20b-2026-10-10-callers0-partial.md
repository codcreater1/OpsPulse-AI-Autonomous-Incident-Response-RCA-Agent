# RCA evaluation - live mode

- Run at: 2026-10-10T12:41:35.687662+00:00  |  dataset: rca-callers-v1 (4 cases)
- Versions: {"agent_version": "1.1.0-opspulse", "prompt_version": "rca-prompt-v5", "evaluator_version": "quality-gate-v5", "retrieval_strategy": "lexical-v1", "model": "openai/gpt-oss-20b", "quality_threshold": 0.85, "max_analysis_iterations": 3, "max_output_tokens": 4096}

| Metric | Value | n/d | Definition |
|---|---|---|---|
| structured_output_validity | 1.000 | 2/2 | LLM attempts whose reply validated against RCAOutput / LLM attempts (provider errors excluded) |
| category_accuracy | 1.000 | 1/1 | final category == labelled category / cases labelled conclusive |
| evidence_grounding_accuracy | 1.000 | 2/2 | 'observed' quotes found verbatim in their cited source / all 'observed' quotes (final analyses) |
| unsupported_claim_rate | 0.000 | 0/3 | (unverifiable 'observed' quotes + affected files absent from trace/retrieved file) / (all quotes + all affected files) |
| abstention_recall | n/a | 0/0 | inconclusive-labelled cases where the model declared insufficient evidence or category 'unknown' / inconclusive-labelled cases |
| inconclusive_not_accepted_rate | n/a | 0/0 | inconclusive-labelled cases the quality gate did NOT accept / inconclusive-labelled cases |
| false_abstention_rate | 0.000 | 0/1 | conclusive-labelled cases where the model abstained / conclusive-labelled cases |
| gate_acceptance_rate | 1.000 | 1/1 | cases accepted by the quality gate / evaluated cases |
| false_acceptance_rate | 0.000 | 0/1 | accepted cases that are inconclusive-labelled or have the wrong category / accepted cases |
| relevant_file_hit_rate | 0.000 | 0/1 | cases whose affected_files contain a labelled relevant file / cases with labelled files |
| unsupported_acceptance_rate | n/a | 0/0 | unsupported analyses (inconclusive-labelled or with an unverifiable quote) the gate accepted / unsupported analyses |
| workflow_failure_rate | 0.750 | 3/4 | cases ending in workflow status 'failed' (e.g. provider errors) / cases |

- Average attempts: 1.25
- Not evaluated (provider prevented completion): ['caller-empty-list', 'caller-two-levels-up', 'control-cause-in-trigger']
- LLM latency ms: {'mean': 22911, 'p95': 39982, 'samples': 2}  |  case wall ms: {'mean': 11530, 'p95': 45832}
- Tokens: {'input': 4673, 'output': 5381, 'attempts_with_usage': 2}  |  estimated cost USD: None

| Case | Expected | Predicted | Gate | Status | Attempts | Quotes ok |
|---|---|---|---|---|---|---|
| caller-passes-none | null_reference | null_reference | pass | accepted | 2 | 2/2 |
| caller-empty-list | logic_error | None | fail | failed | 1 | 0/0 |
| caller-two-levels-up | type_error | None | fail | failed | 1 | 0/0 |
| control-cause-in-trigger | logic_error | None | fail | failed | 1 | 0/0 |
