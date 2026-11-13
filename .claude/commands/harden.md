---
description: Wire the tooling baseline (CI, lint, coverage, secret and dependency scanning) into an app, measure its baseline, and report what needs the owner. Additive; never edits app source.
argument-hint: <app-name>
---

**App root:** if this repo has `docs/foundry/app-context.md` it is the app; otherwise you are in the
Foundry HQ and the argument is a name from `apps.md` (resolve its path). Brief any agent with the
absolute app root. Work only there.

Read `docs/foundry/tooling/README.md` (policy) and `docs/foundry/app-context.md` (stack, commands).
If `docs/foundry/tooling/` is missing, run `./install.sh --update <app>` from the HQ first.

Rules: **add files only.** Do not edit application source, tests, or existing CI. Do not commit,
push, change git config, or activate hooks. Download nothing except running `uvx ruff`,
`uvx pip-audit` and `gitleaks` locally for measurement.

1. **Detect** the stack (Python, Node, or both) and the real commands from app-context; mark
   anything you cannot confirm `UNVERIFIED`. Look in `.github/workflows/`; a missing directory means no CI (create it).
2. **CI.** Create `.github/workflows/` if missing. If no workflow runs the tests, create `.github/workflows/quality.yml` from the matching
   template, replacing every `__PLACEHOLDER__` from verified facts. Python version comes from the Stack line. Runner: `macos-latest` for macOS-only or native-Qt apps, else `ubuntu-latest`. The install command must also install `coverage` (it is often missing from dev requirements), and the test command must write coverage data, e.g. `python -m coverage run --source=<packages> -m pytest`. If CI already exists, leave it
   and add only `security.yml`. Always add `security.yml` (fill `__AUDIT_CMD__`: `pip install
   pip-audit && pip-audit -r requirements.txt`, or `npm audit --audit-level=high`),
   `.github/dependabot.yml` (fill ecosystems; the format is in the template's header comment), and `.gitleaks.toml` (template as is: no empty `[allowlist]` table).
3. **Python lint.** If the app has no ruff config, copy `python/ruff.toml` to the app root.
4. **Hook.** Copy `common/githooks/pre-commit` to `.githooks/pre-commit` (executable). Do not activate.
5. **Measure the baseline, report-only.** If `ruff` is not on PATH use `uvx ruff`. Lint count:
   `ruff check --no-cache --quiet --output-format=concise --exit-zero .` (one line per finding), `gitleaks detect --no-git --redact -c .gitleaks.toml` (never print secret values),
   `uvx pip-audit -r requirements.txt` or `npm audit --json`, and coverage only if the suite is
   fast (otherwise `UNVERIFIED`). Record counts with `python docs/foundry/tooling/ratchet.py
   --update ruff ruff check --no-cache --quiet --output-format=concise --exit-zero .` (or `uvx ruff` instead of `ruff`) (creates `baseline.json`).
6. **Write `docs/foundry/tooling-baseline.md`:** date, exact commands and their output counts, what
   was added, what is `UNVERIFIED`, and the coverage floor (measured minus 1, or `UNVERIFIED`).
7. **Verify** every YAML parses (`ruby -ryaml -e 'YAML.load_file(ARGV[0])' <file>`; PyYAML is often missing) and no
   `__PLACEHOLDER__` remains (`grep -rn "__[A-Z_]*__" .github .gitleaks.toml`).
8. **Report** in 10 lines: files added (note `baseline.json` must be committed with them), baseline numbers, and **owner actions**: branch protection
   (require `quality` + review), repo secrets if any, activate the hook with `git config
   core.hooksPath .githooks`, any gitleaks findings (rotate, do not allowlist), missing remote.

## Notes from the first runs (apply them)
- **Never leave caches or data in the app:** run ruff with `--no-cache`; write coverage data to a
  temp dir (`COVERAGE_FILE=$(mktemp -d)/.coverage`). Check `git status --short` before and after.
- **Mixed stacks (Python + Node):** merge both templates into ONE `quality.yml` with separate
  jobs (they share the filename). Put both audits in `security.yml` as separate steps.
- **unittest or non-Qt apps:** replace `__TEST_CMD__` with `python -m coverage run -m unittest
  discover -s tests` and drop the `QT_QPA_PLATFORM` line; drop the coverage-floor step if no floor
  could be measured, and say so in `tooling-baseline.md`.
- **gitleaks scope:** `--no-git` scans git-ignored and build output (`build/`, `dist*/`, `.venv`,
  `__pycache__`, `.env`) and can take minutes. Measure with `gitleaks detect --redact -c
  .gitleaks.toml` (history, matches CI) and, for the working tree, a scratch config in a temp dir
  that excludes those paths. Never put exclusions in the repo's `.gitleaks.toml` without the owner.
  Report path and rule only; a finding in `.env` or other ignored files is not a repo leak but
  still worth rotating if shared.
- **Submodules:** add no files inside them; use `submodules: false` in checkout steps.
- **Branch triggers:** read existing workflows' `on:` branches and compare with the repo's real
  branch; report a mismatch (for example `main` vs `master`).
- **No `timeout` on macOS:** cap a run with `perl -e 'alarm shift; exec @ARGV' 300 <cmd>`.
- **Stale context:** if measurements contradict `app-context.md` (test counts, missing tools),
  report each contradiction; do not edit app-context.
- **Baselines:** `baseline.json` lives in `docs/foundry/tooling/`; `install.sh --update` never
  overwrites it, and it must be committed.
