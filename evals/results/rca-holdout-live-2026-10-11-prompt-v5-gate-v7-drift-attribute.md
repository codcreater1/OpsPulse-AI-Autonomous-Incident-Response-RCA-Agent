# RCA evaluation - live mode

- Run at: 2026-10-10T22:09:58.091162+00:00  |  dataset: rca-holdout-v1 (1 cases)
- Versions: {"agent_version": "1.2.0-opspulse", "prompt_version": "rca-prompt-v5", "evaluator_version": "quality-gate-v7", "retrieval_strategy": "lexical-v1", "model": "openai/gpt-oss-120b", "quality_threshold": 0.85, "max_analysis_iterations": 3, "max_output_tokens": 4096}

| Metric | Value | n/d | Definition |
|---|---|---|---|
| structured_output_validity | 1.000 | 1/1 | LLM attempts whose reply validated against RCAOutput / LLM attempts (provider errors excluded) |
| category_accuracy | n/a | 0/0 | final category == labelled category / cases labelled conclusive |
| evidence_grounding_accuracy | n/a | 0/0 | 'observed' quotes found verbatim in their cited source / all 'observed' quotes (final analyses) |
| unsupported_claim_rate | n/a | 0/0 | (unverifiable 'observed' quotes + affected files absent from trace/retrieved file) / (all quotes + all affected files) |
| abstention_recall | n/a | 0/0 | inconclusive-labelled cases where the model declared insufficient evidence or category 'unknown' / inconclusive-labelled cases |
| inconclusive_not_accepted_rate | n/a | 0/0 | inconclusive-labelled cases the quality gate did NOT accept / inconclusive-labelled cases |
| false_abstention_rate | n/a | 0/0 | conclusive-labelled cases where the model abstained / conclusive-labelled cases |
| gate_acceptance_rate | n/a | 0/0 | cases accepted by the quality gate / evaluated cases |
| false_acceptance_rate | n/a | 0/0 | accepted cases that are inconclusive-labelled or have the wrong category / accepted cases |
| relevant_file_hit_rate | n/a | 0/0 | cases whose affected_files contain a labelled relevant file / cases with labelled files |
| unsupported_acceptance_rate | n/a | 0/0 | unsupported analyses (inconclusive-labelled or with an unverifiable quote) the gate accepted / unsupported analyses |
| workflow_failure_rate | 1.000 | 1/1 | cases ending in workflow status 'failed' (e.g. provider errors) / cases |

- Average attempts: 2.0
- Not evaluated (provider prevented completion): ['ho-drift-attribute']
- LLM latency ms: {'mean': 98421, 'p95': 98421, 'samples': 1}  |  case wall ms: {'mean': 98945, 'p95': 98945}
- Tokens: {'input': 2006, 'output': 1554, 'attempts_with_usage': 1}  |  estimated cost USD: None

| Case | Expected | Predicted | Gate | Status | Attempts | Quotes ok |
|---|---|---|---|---|---|---|
| ho-drift-attribute | attribute_error (inconclusive) | attribute_error | fail | failed | 2 | 2/2 |
