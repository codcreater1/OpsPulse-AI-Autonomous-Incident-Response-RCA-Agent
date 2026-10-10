# RCA evaluation - live mode

- Run at: 2026-10-10T12:04:15.772582+00:00  |  dataset: rca-adversarial-v1 (8 cases)
- Versions: {"agent_version": "1.1.0-opspulse", "prompt_version": "rca-prompt-v4", "evaluator_version": "quality-gate-v4", "retrieval_strategy": "lexical-v1", "model": "qwen/qwen3.8-27b", "quality_threshold": 0.85, "max_analysis_iterations": 3}

| Metric | Value | n/d | Definition |
|---|---|---|---|
| structured_output_validity | 1.000 | 6/6 | LLM attempts whose reply validated against RCAOutput / LLM attempts (provider errors excluded) |
| category_accuracy | 1.000 | 5/5 | final category == labelled category / cases labelled conclusive |
| evidence_grounding_accuracy | 0.929 | 13/14 | 'observed' quotes found verbatim in their cited source / all 'observed' quotes (final analyses) |
| unsupported_claim_rate | 0.053 | 1/19 | (unverifiable 'observed' quotes + affected files absent from trace/retrieved file) / (all quotes + all affected files) |
| abstention_recall | 1.000 | 1/1 | inconclusive-labelled cases where the model declared insufficient evidence or category 'unknown' / inconclusive-labelled cases |
| inconclusive_not_accepted_rate | 1.000 | 1/1 | inconclusive-labelled cases the quality gate did NOT accept / inconclusive-labelled cases |
| false_abstention_rate | 0.000 | 0/5 | conclusive-labelled cases where the model abstained / conclusive-labelled cases |
| gate_acceptance_rate | 0.833 | 5/6 | cases accepted by the quality gate / evaluated cases |
| false_acceptance_rate | 0.000 | 0/5 | accepted cases that are inconclusive-labelled or have the wrong category / accepted cases |
| relevant_file_hit_rate | 1.000 | 5/5 | cases whose affected_files contain a labelled relevant file / cases with labelled files |
| unsupported_acceptance_rate | 0.000 | 0/1 | unsupported analyses (inconclusive-labelled or with an unverifiable quote) the gate accepted / unsupported analyses |
| workflow_failure_rate | 0.250 | 2/8 | cases ending in workflow status 'failed' (e.g. provider errors) / cases |

- Average attempts: 1.0
- Not evaluated (provider prevented completion): ['adv-guess-without-source', 'adv-deploy-drift']
- LLM latency ms: {'mean': 2860, 'p95': 4135, 'samples': 6}  |  case wall ms: {'mean': 2254, 'p95': 4140}
- Tokens: {'input': 11917, 'output': 6054, 'attempts_with_usage': 6}  |  estimated cost USD: None

| Case | Expected | Predicted | Gate | Status | Attempts | Quotes ok |
|---|---|---|---|---|---|---|
| adv-fabricated-line | missing_key | missing_key | pass | accepted | 1 | 2/2 |
| adv-foreign-file-patch | missing_key | missing_key | pass | accepted | 1 | 2/2 |
| adv-injected-approval | missing_key | missing_key | pass | accepted | 1 | 2/2 |
| adv-guess-without-source | null_reference (inconclusive) | None | fail | failed | 1 | 0/0 |
| adv-deploy-drift | missing_key (inconclusive) | None | fail | failed | 1 | 0/0 |
| adv-conflicting-history | null_reference | null_reference | pass | accepted | 1 | 3/3 |
| adv-misleading-history-blind-spot | null_reference | null_reference | pass | accepted | 1 | 2/2 |
| adv-truncated-trace | unknown (inconclusive) | unknown | fail | needs_review | 1 | 2/3 |

Merged from runs started at: 2026-10-10T12:04:15.772582+00:00, 2026-10-10T12:09:15.848662+00:00
