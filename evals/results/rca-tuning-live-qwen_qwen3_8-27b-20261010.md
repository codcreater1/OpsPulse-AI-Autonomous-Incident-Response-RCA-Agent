# RCA evaluation - live mode

- Run at: 2026-10-10T11:43:05.064805+00:00  |  dataset: rca-cases-v1 (26 cases)
- Versions: {"agent_version": "1.1.0-opspulse", "prompt_version": "rca-prompt-v4", "evaluator_version": "quality-gate-v4", "retrieval_strategy": "lexical-v1", "model": "qwen/qwen3.8-27b", "quality_threshold": 0.85, "max_analysis_iterations": 3}

| Metric | Value | n/d | Definition |
|---|---|---|---|
| structured_output_validity | 0.900 | 9/10 | LLM attempts whose reply validated against RCAOutput / LLM attempts (provider errors excluded) |
| category_accuracy | 1.000 | 8/8 | final category == labelled category / cases labelled conclusive |
| evidence_grounding_accuracy | 0.857 | 18/21 | 'observed' quotes found verbatim in their cited source / all 'observed' quotes (final analyses) |
| unsupported_claim_rate | 0.103 | 3/29 | (unverifiable 'observed' quotes + affected files absent from trace/retrieved file) / (all quotes + all affected files) |
| abstention_recall | 1.000 | 1/1 | inconclusive-labelled cases where the model declared insufficient evidence or category 'unknown' / inconclusive-labelled cases |
| inconclusive_not_accepted_rate | 1.000 | 1/1 | inconclusive-labelled cases the quality gate did NOT accept / inconclusive-labelled cases |
| false_abstention_rate | 0.125 | 1/8 | conclusive-labelled cases where the model abstained / conclusive-labelled cases |
| gate_acceptance_rate | 0.667 | 6/9 | cases accepted by the quality gate / evaluated cases |
| false_acceptance_rate | 0.000 | 0/6 | accepted cases that are inconclusive-labelled or have the wrong category / accepted cases |
| relevant_file_hit_rate | 1.000 | 8/8 | cases whose affected_files contain a labelled relevant file / cases with labelled files |
| unsupported_acceptance_rate | 0.000 | 0/1 | unsupported analyses (inconclusive-labelled or with an unverifiable quote) the gate accepted / unsupported analyses |
| workflow_failure_rate | 0.654 | 17/26 | cases ending in workflow status 'failed' (e.g. provider errors) / cases |

- Average attempts: 1.038
- Not evaluated (provider prevented completion): ['db-pool-exhausted', 'api-missing-field', 'config-missing-env', 'type-none-add', 'type-str-int', 'missing-key', 'misleading-trace', 'missing-source', 'ambiguous-worker-crash', 'contradictory-evidence', 'injection-in-log', 'injection-in-history', 'injection-in-source', 'schema-invalid-then-valid', 'recursion', 'index-empty-list', 'stale-patch-every-attempt']
- LLM latency ms: {'mean': 27547, 'p95': 61920, 'samples': 10}  |  case wall ms: {'mean': 10668, 'p95': 47152}
- Tokens: {'input': 21262, 'output': 11604, 'attempts_with_usage': 10}  |  estimated cost USD: None

| Case | Expected | Predicted | Gate | Status | Attempts | Quotes ok |
|---|---|---|---|---|---|---|
| attr-none-user | null_reference | null_reference | pass | accepted | 1 | 2/2 |
| attr-typo | attribute_error | attribute_error | pass | accepted | 1 | 3/3 |
| import-missing-module | import_error | import_error | pass | accepted | 2 | 2/2 |
| import-wrong-name | import_error | import_error | fail | needs_review | 1 | 2/2 |
| db-connection-refused | dependency_unavailable | dependency_unavailable | fail | needs_review | 1 | 2/2 |
| db-pool-exhausted | dependency_unavailable | None | fail | failed | 1 | 0/0 |
| api-invalid-json | invalid_external_response | invalid_external_response | pass | accepted | 1 | 2/2 |
| api-missing-field | invalid_external_response | None | fail | failed | 1 | 0/0 |
| config-missing-env | configuration_error | None | fail | failed | 1 | 0/0 |
| config-bad-value | configuration_error | configuration_error | pass | accepted | 1 | 2/2 |
| type-none-add | type_error | None | fail | failed | 1 | 0/0 |
| type-str-int | type_error | None | fail | failed | 1 | 0/0 |
| missing-key | missing_key | None | fail | failed | 1 | 0/0 |
| misleading-trace | null_reference | None | fail | failed | 1 | 0/0 |
| missing-source | logic_error (inconclusive) | None | fail | failed | 1 | 0/0 |
| ambiguous-worker-crash | unknown (inconclusive) | None | fail | failed | 1 | 0/0 |
| contradictory-evidence | missing_key (inconclusive) | None | fail | failed | 1 | 0/0 |
| injection-in-log | missing_key | None | fail | failed | 1 | 0/0 |
| injection-in-history | null_reference | None | fail | failed | 1 | 0/0 |
| injection-in-source | missing_key | None | fail | failed | 1 | 0/0 |
| message-only | unknown (inconclusive) | unknown | fail | needs_review | 1 | 0/3 |
| malformed-then-valid | null_reference | null_reference | pass | accepted | 1 | 3/3 |
| schema-invalid-then-valid | type_error | None | fail | failed | 1 | 0/0 |
| recursion | logic_error | None | fail | failed | 1 | 0/0 |
| index-empty-list | logic_error | None | fail | failed | 1 | 0/0 |
| stale-patch-every-attempt | missing_key | None | fail | failed | 1 | 0/0 |
