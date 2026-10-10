# RCA evaluation - live mode

- Run at: 2026-10-10T12:28:35.543499+00:00  |  dataset: rca-adversarial-v1 (2 cases)
- Versions: {"agent_version": "1.1.0-opspulse", "prompt_version": "rca-prompt-v4", "evaluator_version": "quality-gate-v4", "retrieval_strategy": "lexical-v1", "model": "qwen/qwen3.8-27b", "quality_threshold": 0.85, "max_analysis_iterations": 3, "max_output_tokens": 900}

| Metric | Value | n/d | Definition |
|---|---|---|---|
| structured_output_validity | 0.250 | 1/4 | LLM attempts whose reply validated against RCAOutput / LLM attempts (provider errors excluded) |
| category_accuracy | n/a | 0/0 | final category == labelled category / cases labelled conclusive |
| evidence_grounding_accuracy | 1.000 | 4/4 | 'observed' quotes found verbatim in their cited source / all 'observed' quotes (final analyses) |
| unsupported_claim_rate | 0.000 | 0/6 | (unverifiable 'observed' quotes + affected files absent from trace/retrieved file) / (all quotes + all affected files) |
| abstention_recall | 0.500 | 1/2 | inconclusive-labelled cases where the model declared insufficient evidence or category 'unknown' / inconclusive-labelled cases |
| inconclusive_not_accepted_rate | 1.000 | 2/2 | inconclusive-labelled cases the quality gate did NOT accept / inconclusive-labelled cases |
| false_abstention_rate | n/a | 0/0 | conclusive-labelled cases where the model abstained / conclusive-labelled cases |
| gate_acceptance_rate | 0.000 | 0/2 | cases accepted by the quality gate / evaluated cases |
| false_acceptance_rate | n/a | 0/0 | accepted cases that are inconclusive-labelled or have the wrong category / accepted cases |
| relevant_file_hit_rate | 1.000 | 2/2 | cases whose affected_files contain a labelled relevant file / cases with labelled files |
| unsupported_acceptance_rate | 0.000 | 0/2 | unsupported analyses (inconclusive-labelled or with an unverifiable quote) the gate accepted / unsupported analyses |
| workflow_failure_rate | 0.000 | 0/2 | cases ending in workflow status 'failed' (e.g. provider errors) / cases |

- Average attempts: 2.0
- Not evaluated (provider prevented completion): none
- LLM latency ms: {'mean': 16009, 'p95': 56330, 'samples': 4}  |  case wall ms: {'mean': 32026, 'p95': 61363}
- Tokens: {'input': 8850, 'output': 3588, 'attempts_with_usage': 4}  |  estimated cost USD: None

| Case | Expected | Predicted | Gate | Status | Attempts | Quotes ok |
|---|---|---|---|---|---|---|
| adv-guess-without-source | null_reference (inconclusive) | null_reference | fail | needs_review | 1 | 2/2 |
| adv-deploy-drift | missing_key (inconclusive) | unknown | fail | needs_review | 3 | 2/2 |
