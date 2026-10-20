# Ablation on the callers set (`rca-callers-v3`, prompt `rca-prompt-v6.1`, gate `quality-gate-v8`)

Question: what do self-correction and caller context actually contribute? Same five cases, three runs each, `gpt-oss-120b`
on the Groq free tier. The baseline is the 2026-10-17 run; the two ablations were run on 2026-10-20 (the provider and its
load may differ between days). **Counts are runs, not rates; with 13 to 15 runs per column no difference below a few runs
means anything.**

| | baseline (3 attempts, caller context) | no self-correction (`MAX_ANALYSIS_ITERATIONS=1`) | no caller context (`CALLER_CONTEXT_FRAMES=0`) |
|---|---|---|---|
| Evaluated runs (provider failures excluded) | 13 (2 not evaluated) | 15 | 13 (2 not evaluated) |
| Correct category | 13/13 | 15/15 | 13/13 |
| Fix file named correctly | 13/13 | 14/15 | 13/13 |
| Accepted by the gate | 2 | 4 | 3 |
| Unsafe accepted (callee patched, caller at fault) | 0 | **1** | 0 |
| Control case (fault in the failing function) accepted | 2/2 | 3/3 | 3/3 |
| "Observed" quotes verified | 34/34 | 40/41 | 28/28 |
| Verified quotes per run | 2.6 | 2.7 | 2.2 |
| Mean attempts per run | 1.15 | 1.00 | 1.00 |

Per case, runs / accepted:

| case | baseline | no self-correction | no caller context |
|---|---|---|---|
| caller-empty-list | 3 / 0 | 3 / **1** | 2 / 0 |
| caller-passes-none | 3 / 0 | 3 / 0 | 3 / 0 |
| caller-symptomatic-patch | 3 / 0 | 3 / 0 | 3 / 0 |
| caller-two-levels-up | 2 / 0 | 3 / 0 | 2 / 0 |
| control-cause-in-trigger | 2 / 2 | 3 / 3 | 3 / 3 |

## What this does and does not show

- **Self-correction was rarely needed here.** The model's first attempt passed the gate or failed it for reasons a retry
  does not fix in nearly every run (mean 1.15 attempts). Switching it off changed two things, both small: one quote that the
  retry would have repaired stayed unverified (40/41), and `caller-empty-list` was accepted once with a callee patch (an
  unsafe acceptance). The same case was accepted 0 of 3 in the baseline and 3 of 3 under prompt v6 (see the 2026-10-15
  report), so a single acceptance in three runs is within the run-to-run variation this model already shows. **It is
  suggestive, not demonstrated, that the retry loop protects against that mistake.**
- **Caller context did not change the outcomes on this set.** Without it the model still named the right file in 13/13 runs
  and still declined to patch the callee in every blame case; the trace already shows the calling frame and prompt v6.1
  tells the model to decide where the fault is. What caller context measurably adds is *verifiable evidence*: about 0.4 more
  verified quotes per run, because the model can quote the caller's code instead of only the trace. If that matters (a
  reviewer wants the caller line quoted and checked) it is worth its prompt space; if only the diagnosis matters, this set
  does not justify it. These five cases were designed with caller context in mind, so this is if anything a favourable test
  for it.
- **Evidence verification was not ablated.** It is the gate's core guarantee (an "observed" quote must occur in its
  source); switching it off would measure nothing about the product as shipped. The relevant counterfactual is in the table:
  the 1 unverifiable quote in the no-self-correction column was caught by the gate and the case went to review.
- Two of 15 runs hit provider limits in the baseline and in the no-caller-context column and are not evaluated.

Raw reports: `rca-callers-v3-live-2026-10-17-prompt-v6.1-repeat3.json`,
`rca-callers-v3-live-2026-10-20-ablation-no-self-correction-repeat3.json`,
`rca-callers-v3-live-2026-10-20-ablation-no-caller-context-repeat3.json` (and their `.md` summaries).
