---
role: qa-engineer
last-reviewed: 2026-10-14
status: current
---

# Playbook: qa-engineer

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
Test plans, mutation checks, coverage, flake control

## Current practices
- Run the suite with `-W error::pytest.PytestDeprecationWarning` (or the `filterwarnings` ini equivalent) in CI, so pytest-10 removals fail now rather than at the upgrade. Session- and module-scoped autouse fixtures live in `conftest.py`, never inline in a test module.
- A red CI check on the default branch is a P1 bug for QA, not background noise. A test that needs a real window server, an installed bundle or a launched app is marked (for example `@pytest.mark.desktop`) and skipped with a reason on CI runners; it is never left failing, and never deleted to get green.
- CI runs the suite on the same Python minor version (and Node major) that the app's venv and installed bundle use. A second, newer version may be added as an extra matrix row, never as a replacement.
- Mutation check: plant at least three mutants in each piece of new logic (flip a comparison, drop a branch, change a constant), by hand or with `mutmut run --paths-to-mutate <file>` on Qt-free modules. Record in the verify report how many were planted and killed, by file:line. A survivor is a missing test, not a pass.
- Flake control: CI runs the suite with a per-test timeout (`pytest-timeout`, `--timeout=120` unless the app documents another value) and in random order (`pytest-randomly`), printing the seed so a failure can be replayed. A test that fails under one seed is a bug in the test or the code, never retried until green.

- Apps that call a model _(baseline 2026-11-11, Foundry v9: not yet verified by a radar run)_:
  unit tests never call a live model or a running model server; they use fakes or recorded
  fixtures (a recorded answer checked into the repo, with the prompt that produced it). A small
  live eval suite (a handful of representative cases with a pass bar written before the run)
  runs on demand and before Release on the cheapest adequate model for that kind of work
  (`docs/playbooks/model-routing.md`), within the plan's `eval_budget_usd`; each run's cost is
  recorded with `docs/foundry/tooling/model_use.py . --purpose eval --cost-usd <n>`. A run with no
  recorded cost counts as over budget until it is entered.

## Watch list
test-framework releases, mutation/property testing, CI test reliability

## Change log
- 2026-10-10: seeded (baseline).
- 2026-11-11: model testing rule (fixtures in unit tests, budgeted live evals) added with Foundry
  v9; baseline.
- 2026-10-14: current practices added from `radar/reports/2026-10-14-ship.md` (owner accepted all proposed edits).
