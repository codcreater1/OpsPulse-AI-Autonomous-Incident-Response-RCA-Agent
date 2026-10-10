# RCA evaluation - live mode

- Run at: 2026-10-10T10:25:52.688962+00:00  |  dataset: rca-holdout-v1 (12 cases)
- Versions: {"agent_version": "1.1.0-opspulse", "prompt_version": "rca-prompt-v4", "evaluator_version": "quality-gate-v4", "retrieval_strategy": "lexical-v1", "model": "openai/gpt-oss-120b", "quality_threshold": 0.85, "max_analysis_iterations": 3}

| Metric | Value | n/d | Definition |
|---|---|---|---|
| structured_output_validity | 1.000 | 6/6 | LLM attempts whose reply validated against RCAOutput / LLM attempts (provider errors excluded) |
| category_accuracy | 1.000 | 6/6 | final category == labelled category / cases labelled conclusive |
| evidence_grounding_accuracy | 1.000 | 13/13 | 'observed' quotes found verbatim in their cited source / all 'observed' quotes (final analyses) |
| unsupported_claim_rate | 0.000 | 0/19 | (unverifiable 'observed' quotes + affected files absent from trace/retrieved file) / (all quotes + all affected files) |
| abstention_recall | n/a | 0/0 | inconclusive-labelled cases where the model declared insufficient evidence or category 'unknown' / inconclusive-labelled cases |
| inconclusive_not_accepted_rate | n/a | 0/0 | inconclusive-labelled cases the quality gate did NOT accept / inconclusive-labelled cases |
| false_abstention_rate | 0.000 | 0/6 | conclusive-labelled cases where the model abstained / conclusive-labelled cases |
| gate_acceptance_rate | 1.000 | 6/6 | cases accepted by the quality gate / evaluated cases |
| false_acceptance_rate | 0.000 | 0/6 | accepted cases that are inconclusive-labelled or have the wrong category / accepted cases |
| relevant_file_hit_rate | 1.000 | 6/6 | cases whose affected_files contain a labelled relevant file / cases with labelled files |
| workflow_failure_rate | 0.500 | 6/12 | cases ending in workflow status 'failed' (e.g. provider errors) / cases |

- Average attempts: 1.0
- Not evaluated (provider prevented completion): ['ho-str-price', 'ho-off-by-one', 'ho-missing-package', 'ho-gateway-timeout', 'ho-drift-attribute', 'ho-pool-timeout']
- LLM latency ms: {'mean': 3942, 'p95': 4838, 'samples': 6}  |  case wall ms: {'mean': 2021, 'p95': 4842}
- Tokens: {'input': 11801, 'output': 9330, 'attempts_with_usage': 6}  |  estimated cost USD: None

| Case | Expected | Predicted | Gate | Status | Attempts | Quotes ok |
|---|---|---|---|---|---|---|
| ho-none-config | null_reference | null_reference | pass | accepted | 1 | 2/2 |
| ho-env-int | configuration_error | configuration_error | pass | accepted | 1 | 2/2 |
| ho-redis-down | dependency_unavailable | dependency_unavailable | pass | accepted | 1 | 2/2 |
| ho-upstream-shape | invalid_external_response | invalid_external_response | pass | accepted | 1 | 3/3 |
| ho-typo-method | attribute_error | attribute_error | pass | accepted | 1 | 2/2 |
| ho-internal-key | missing_key | missing_key | pass | accepted | 1 | 2/2 |
| ho-str-price | type_error | None | fail | failed | 1 | 0/0 |
| ho-off-by-one | logic_error | None | fail | failed | 1 | 0/0 |
| ho-missing-package | import_error | None | fail | failed | 1 | 0/0 |
| ho-gateway-timeout | unknown (inconclusive) | None | fail | failed | 1 | 0/0 |
| ho-drift-attribute | attribute_error (inconclusive) | None | fail | failed | 1 | 0/0 |
| ho-pool-timeout | dependency_unavailable | None | fail | failed | 1 | 0/0 |
