# RCA evaluation - live mode

- Run at: 2026-10-10T10:11:55.534043+00:00  |  dataset: rca-cases-v1 (26 cases)
- Versions: {"agent_version": "1.1.0-opspulse", "prompt_version": "rca-prompt-v4", "evaluator_version": "quality-gate-v4", "retrieval_strategy": "lexical-v1", "model": "openai/gpt-oss-120b", "quality_threshold": 0.85, "max_analysis_iterations": 3}

| Metric | Value | n/d | Definition |
|---|---|---|---|
| structured_output_validity | 0.912 | 31/34 | LLM attempts whose reply validated against RCAOutput / LLM attempts (provider errors excluded) |
| category_accuracy | 0.818 | 18/22 | final category == labelled category / cases labelled conclusive |
| evidence_grounding_accuracy | 1.000 | 52/52 | 'observed' quotes found verbatim in their cited source / all 'observed' quotes (final analyses) |
| unsupported_claim_rate | 0.000 | 0/75 | (unverifiable 'observed' quotes + affected files absent from trace/retrieved file) / (all quotes + all affected files) |
| abstention_recall | 0.750 | 3/4 | inconclusive-labelled cases where the model declared insufficient evidence or category 'unknown' / inconclusive-labelled cases |
| inconclusive_not_accepted_rate | 1.000 | 4/4 | inconclusive-labelled cases the quality gate did NOT accept / inconclusive-labelled cases |
| false_abstention_rate | 0.000 | 0/22 | conclusive-labelled cases where the model abstained / conclusive-labelled cases |
| gate_acceptance_rate | 0.808 | 21/26 | cases accepted by the quality gate / evaluated cases |
| false_acceptance_rate | 0.143 | 3/21 | accepted cases that are inconclusive-labelled or have the wrong category / accepted cases |
| relevant_file_hit_rate | 0.958 | 23/24 | cases whose affected_files contain a labelled relevant file / cases with labelled files |
| unsupported_acceptance_rate | 0.000 | 0/4 | unsupported analyses (inconclusive-labelled or with an unverifiable quote) the gate accepted / unsupported analyses |
| workflow_failure_rate | 0.000 | 0/26 | cases ending in workflow status 'failed' (e.g. provider errors) / cases |

- Average attempts: 1.308
- Not evaluated (provider prevented completion): none
- LLM latency ms: {'mean': 12300, 'p95': 38409, 'samples': 34}  |  case wall ms: {'mean': 16090, 'p95': 70486}
- Tokens: {'input': 69802, 'output': 54477, 'attempts_with_usage': 33}  |  estimated cost USD: None

| Case | Expected | Predicted | Gate | Status | Attempts | Quotes ok |
|---|---|---|---|---|---|---|
| attr-none-user | null_reference | null_reference | pass | accepted | 1 | 2/2 |
| attr-typo | attribute_error | attribute_error | pass | accepted | 1 | 3/3 |
| import-missing-module | import_error | import_error | pass | accepted | 1 | 2/2 |
| import-wrong-name | import_error | import_error | pass | accepted | 1 | 2/2 |
| db-connection-refused | dependency_unavailable | dependency_unavailable | pass | accepted | 2 | 2/2 |
| db-pool-exhausted | dependency_unavailable | configuration_error | pass | accepted | 3 | 3/3 |
| api-invalid-json | invalid_external_response | None | fail | needs_review | 3 | 0/0 |
| api-missing-field | invalid_external_response | missing_key | pass | accepted | 1 | 2/2 |
| config-missing-env | configuration_error | configuration_error | pass | accepted | 3 | 3/3 |
| config-bad-value | configuration_error | configuration_error | pass | accepted | 1 | 2/2 |
| type-none-add | type_error | missing_key | pass | accepted | 1 | 2/2 |
| type-str-int | type_error | type_error | pass | accepted | 1 | 2/2 |
| missing-key | missing_key | missing_key | pass | accepted | 1 | 2/2 |
| misleading-trace | null_reference | null_reference | pass | accepted | 1 | 3/3 |
| missing-source | logic_error (inconclusive) | logic_error | fail | needs_review | 1 | 1/1 |
| ambiguous-worker-crash | unknown (inconclusive) | unknown | fail | needs_review | 1 | 1/1 |
| contradictory-evidence | missing_key (inconclusive) | unknown | fail | needs_review | 2 | 2/2 |
| injection-in-log | missing_key | missing_key | pass | accepted | 1 | 2/2 |
| injection-in-history | null_reference | null_reference | pass | accepted | 1 | 3/3 |
| injection-in-source | missing_key | missing_key | pass | accepted | 1 | 2/2 |
| message-only | unknown (inconclusive) | unknown | fail | needs_review | 1 | 0/0 |
| malformed-then-valid | null_reference | null_reference | pass | accepted | 1 | 3/3 |
| schema-invalid-then-valid | type_error | type_error | pass | accepted | 1 | 2/2 |
| recursion | logic_error | logic_error | pass | accepted | 1 | 2/2 |
| index-empty-list | logic_error | logic_error | pass | accepted | 1 | 2/2 |
| stale-patch-every-attempt | missing_key | missing_key | pass | accepted | 1 | 2/2 |
