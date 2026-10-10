# RCA evaluation - live mode

- Run at: 2026-10-10T12:37:52.348371+00:00  |  dataset: rca-callers-v1 (4 cases)
- Versions: {"agent_version": "1.1.0-opspulse", "prompt_version": "rca-prompt-v5", "evaluator_version": "quality-gate-v5", "retrieval_strategy": "lexical-v1", "model": "openai/gpt-oss-20b", "quality_threshold": 0.85, "max_analysis_iterations": 3, "max_output_tokens": 4096}

| Metric | Value | n/d | Definition |
|---|---|---|---|
| structured_output_validity | 0.500 | 4/8 | LLM attempts whose reply validated against RCAOutput / LLM attempts (provider errors excluded) |
| category_accuracy | 0.750 | 3/4 | final category == labelled category / cases labelled conclusive |
| evidence_grounding_accuracy | 0.800 | 8/10 | 'observed' quotes found verbatim in their cited source / all 'observed' quotes (final analyses) |
| unsupported_claim_rate | 0.143 | 2/14 | (unverifiable 'observed' quotes + affected files absent from trace/retrieved file) / (all quotes + all affected files) |
| abstention_recall | n/a | 0/0 | inconclusive-labelled cases where the model declared insufficient evidence or category 'unknown' / inconclusive-labelled cases |
| inconclusive_not_accepted_rate | n/a | 0/0 | inconclusive-labelled cases the quality gate did NOT accept / inconclusive-labelled cases |
| false_abstention_rate | 0.000 | 0/4 | conclusive-labelled cases where the model abstained / conclusive-labelled cases |
| gate_acceptance_rate | 0.750 | 3/4 | cases accepted by the quality gate / evaluated cases |
| false_acceptance_rate | 0.333 | 1/3 | accepted cases that are inconclusive-labelled or have the wrong category / accepted cases |
| relevant_file_hit_rate | 0.250 | 1/4 | cases whose affected_files contain a labelled relevant file / cases with labelled files |
| unsupported_acceptance_rate | 0.000 | 0/1 | unsupported analyses (inconclusive-labelled or with an unverifiable quote) the gate accepted / unsupported analyses |
| workflow_failure_rate | 0.000 | 0/4 | cases ending in workflow status 'failed' (e.g. provider errors) / cases |

- Average attempts: 2.0
- Not evaluated (provider prevented completion): none
- LLM latency ms: {'mean': 17650, 'p95': 39813, 'samples': 8}  |  case wall ms: {'mean': 35308, 'p95': 77640}
- Tokens: {'input': 14693, 'output': 11208, 'attempts_with_usage': 6}  |  estimated cost USD: None

| Case | Expected | Predicted | Gate | Status | Attempts | Quotes ok |
|---|---|---|---|---|---|---|
| caller-passes-none | null_reference | missing_key | pass | accepted | 1 | 3/3 |
| caller-empty-list | logic_error | logic_error | fail | needs_review | 3 | 1/3 |
| caller-two-levels-up | type_error | type_error | pass | accepted | 1 | 2/2 |
| control-cause-in-trigger | logic_error | logic_error | pass | accepted | 3 | 2/2 |
