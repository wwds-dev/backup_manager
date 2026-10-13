# Tooling baseline

Machine-checked gates, so quality does not depend on any agent's opinion. Installed into each
app at `docs/company/tooling/` by `install.sh`; `/harden <app>` wires it into the app.

## Policy: a ratchet, not a cliff
Existing apps have debt. The baseline is measured once, recorded in
`docs/company/tooling-baseline.md`, and then may only get better.

| Check | Blocks the build? | Starts at |
|---|---|---|
| Tests | yes | whatever passes today; a red suite is reported, not hidden |
| Lint (ruff / eslint) | only if the violation count rises (`ratchet.py`) | the measured count |
| Types (mypy / tsc) | only if the error count rises, once enabled | the measured count |
| Coverage | yes, below the floor | measured value minus 1 point |
| Secrets (gitleaks) | **yes**, any finding | zero (allowlist needs the owner) |
| Dependency audit | no (reported weekly and on PRs) | the measured findings |

## Files
- `python/quality.yml`, `node/quality.yml`: CI templates with `__PLACEHOLDERS__` that `/harden` fills from the app's `app-context.md`. No placeholder may remain.
- `common/security.yml`: gitleaks on every push, dependency audit weekly.
- `common/dependabot.yml`, `common/.gitleaks.toml`, `python/ruff.toml`.
- `common/githooks/pre-commit`: secrets and lint on staged files. **Not activated automatically**: the owner runs `git config core.hooksPath .githooks` (it would also gate autosync commits).
- `ratchet.py`: fail if a count rose above `baseline.json`; `--update` lowers it. Always count with `ruff check --no-cache --quiet --output-format=concise --exit-zero .` (without `--quiet` ruff adds summary lines that inflate the count). `baseline.json` lives beside it and **must be committed**, or the CI ratchet fails.

## What stays with the owner
GitHub branch protection (require CI + review before merge), enabling the GitHub connector,
adding repo secrets, activating the git hook, and approving any gitleaks allowlist entry.
