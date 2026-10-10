# RCA evaluation - live mode

- Run at: 2026-10-10T15:01:35.094861+00:00  |  dataset: rca-holdout-v1 (1 cases)
- Versions: {"agent_version": "1.2.0-opspulse", "prompt_version": "rca-prompt-v5", "evaluator_version": "quality-gate-v6", "retrieval_strategy": "lexical-v1", "model": "openai/gpt-oss-120b", "quality_threshold": 0.85, "max_analysis_iterations": 3, "max_output_tokens": 4096}

| Metric | Value | n/d | Definition |
|---|---|---|---|
| structured_output_validity | 1.000 | 1/1 | LLM attempts whose reply validated against RCAOutput / LLM attempts (provider errors excluded) |
| category_accuracy | 1.000 | 1/1 | final category == labelled category / cases labelled conclusive |
| evidence_grounding_accuracy | 1.000 | 2/2 | 'observed' quotes found verbatim in their cited source / all 'observed' quotes (final analyses) |
| unsupported_claim_rate | 0.000 | 0/3 | (unverifiable 'observed' quotes + affected files absent from trace/retrieved file) / (all quotes + all affected files) |
| abstention_recall | n/a | 0/0 | inconclusive-labelled cases where the model declared insufficient evidence or category 'unknown' / inconclusive-labelled cases |
| inconclusive_not_accepted_rate | n/a | 0/0 | inconclusive-labelled cases the quality gate did NOT accept / inconclusive-labelled cases |
| false_abstention_rate | 0.000 | 0/1 | conclusive-labelled cases where the model abstained / conclusive-labelled cases |
| gate_acceptance_rate | 1.000 | 1/1 | cases accepted by the quality gate / evaluated cases |
| false_acceptance_rate | 0.000 | 0/1 | accepted cases that are inconclusive-labelled or have the wrong category / accepted cases |
| relevant_file_hit_rate | 1.000 | 1/1 | cases whose affected_files contain a labelled relevant file / cases with labelled files |
| unsupported_acceptance_rate | n/a | 0/0 | unsupported analyses (inconclusive-labelled or with an unverifiable quote) the gate accepted / unsupported analyses |
| workflow_failure_rate | 0.000 | 0/1 | cases ending in workflow status 'failed' (e.g. provider errors) / cases |

- Average attempts: 1.0
- Not evaluated (provider prevented completion): none
- LLM latency ms: {'mean': 5261, 'p95': 5261, 'samples': 1}  |  case wall ms: {'mean': 5269, 'p95': 5269}
- Tokens: {'input': 2026, 'output': 2006, 'attempts_with_usage': 1}  |  estimated cost USD: None

| Case | Expected | Predicted | Gate | Status | Attempts | Quotes ok |
|---|---|---|---|---|---|---|
| ho-missing-package | import_error | import_error | pass | accepted | 1 | 2/2 |
