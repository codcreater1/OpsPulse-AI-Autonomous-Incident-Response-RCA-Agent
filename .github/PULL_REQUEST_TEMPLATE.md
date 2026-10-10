## What and why

## How it was verified

- [ ] `ruff check . && ruff format --check . && mypy && pytest` pass locally
- [ ] Behaviour changes are covered by a test (a failing test before the change, where possible)
- [ ] For gate/prompt/retrieval changes: mock evaluation regression gate passes
      (`python -m evals.compare_reports evals/baselines/rca-<set>-mock.json <new report> --fail-on-regression`),
      versions in `src/versions.py` bumped, and the effect on **live** results stated honestly (or marked untested)
- [ ] README / CHANGELOG updated; no claim without a measurement

## Safety

- [ ] No secrets in code, logs, reports or fixtures
- [ ] Human approval, the repository allow-list and the patch policy are unchanged (or the change is explained)
