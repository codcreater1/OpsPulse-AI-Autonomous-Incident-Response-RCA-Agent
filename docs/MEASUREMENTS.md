# Measurements, in one place

Every number the project has measured, by version, with the interval it can support. The caveats and the per-run detail live
in [Limitations](LIMITATIONS.md) and in `evals/results/`; this page is the short version for someone deciding how far to
trust the system. All live numbers: one model (`openai/gpt-oss-120b`, Groq free tier), small samples, 95 % Wilson intervals.

## The finding that matters

**A passing quality gate does not mean the fix is right.** On real bug-fix history (a commit that fixed a bug and added a
test; the parent commit plus that test is the incident), the gate accepted every analysed run with the right file and no
invented quote, yet few of the accepted patches made the real regression test pass.

| Version | Accepted patches that pass the real regression test (the four cases comparable across versions) | 95 % interval |
|---|---|---|
| prompt v7.1 / gate v8 | 2 of 10 | 6-51 % |
| prompt v7.2 / gate v9 | 2 of 9 | 6-55 % |
| gate v10 experiment (retry on a surviving copy, not merged) | 2 of 10 | 6-51 % |

The three rows are statistically indistinguishable, and every interval is wide: 5 cases from 2 small libraries, 3 runs each.
What it supports is the *direction*: the structural checks do not see wrong behaviour. It does not support any claim that one
version is better than another.

Why the accepted patches failed the real test (8 runs read one by one): a sibling copy of the faulty statement left unfixed (2),
a crash avoided with a wrong value instead of the right output (2), a behaviour choice the code does not determine (3), a new
`UnboundLocalError` (1).

## Everything else

| What | Result | 95 % interval | Where |
|---|---|---|---|
| Holdout set v2, prompt v7.1: category correct (accepted alternatives counted) | 9 of 10, in two runs on two days | 60-98 % | [Limitations](LIMITATIONS.md) |
| Holdout set v2, prompt v7.1: observed quotes verified verbatim | 21 of 21 | 85-100 % | `evals/results/RELIABILITY-holdout-prompt-v7.1.md` |
| Same holdout: runs where the same case got a different outcome on another day | 3 of 12 cases | n/a | [Limitations](LIMITATIONS.md) |
| Callers set, prompt v6.1: category and fix file | 13 of 13 | 77-100 % | `evals/results/RELIABILITY-callers-v3-prompt-v6.1.md` |
| Injected bugs in a real repository: correct fix file | 12 of 12 | 76-100 % | `evals/results/pilot-real-repo-*` |
| Reproduction tests written by the model (injected bugs): reproduced and fixed | 4 of 6 | 30-90 % | `evals/results/REPRO-EVAL-2026-10-23.md` |
| Reviewer memory: earlier rejection followed vs. repeated without it | 9 of 9 vs. 9 of 9 repeated | n/a (mechanism check on synthetic cases) | `evals/results/REVIEWER-MEMORY-2026-10-23.md` |
| Sandbox against a real Docker daemon, opt-in tests | 9 of 9 pass on macOS; the Linux CI job runs the same file | n/a | `tests/integration/test_sandbox_docker.py` |

## What none of this establishes

- That the system helps a team: that needs weeks of real alerts and real review decisions (see the runbook's pilot checklist).
- Any rate with a useful confidence interval; the intervals above are the honest width of 5 to 26 cases.
- Anything about languages other than Python, other models, or production incidents rather than reconstructed bug-fix commits.

## How to reproduce or extend

1. `python -m evals.run_rca --mode live --dataset holdout` with your own key, then `python -m evals.reliability_report`.
2. Real bug-fix history: `docker build -t opspulse-history-tests -f evals/history_tests.Dockerfile evals`, then
   `python -m evals.history_real_repo build` on a clone, `evals.run_rca --dataset-file`, and
   `python -m evals.history_real_repo verify` (third-party tests run in a no-network container).
3. Record the result with its version numbers in `docs/LIMITATIONS.md`, including the runs that went badly.
