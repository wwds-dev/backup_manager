# Tooling baseline

Machine-checked gates, so quality does not depend on any agent's opinion. Installed into each
app at `docs/foundry/tooling/` by `install.sh`; `/harden <app>` wires it into the app.

## Policy: a ratchet, not a cliff
Existing apps have debt. The baseline is measured once, recorded in
`docs/foundry/tooling-baseline.md`, and then may only get better.

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

## Legal sign-off gate
`legal_gate.py` (stdlib) decides whether Release may start, from files only:

| Command | Who runs it | What it does |
|---|---|---|
| `legal_gate.py status <app>` | anyone | tier, pack files, pack hash, last sign-off, open lawyer triggers |
| `legal_gate.py check <app>` | agents, CI, the dashboard | exit 0 when the tier's sign-off rule is met, else 1 with the reasons |
| `legal_gate.py sign <app> --by NAME --role owner\|lawyer [--accept-risk WHY]` | **a person, in a terminal** | appends one line to `docs/legal/signoff.jsonl`, bound to the hash of `docs/legal/` |

`sign` refuses to run without an interactive terminal and asks the signer to type the app's
folder name, so an agent's shell cannot record a sign-off; `install.sh` also adds a deny rule for
it to the app's `.claude/settings.json`. The hash covers every file under `docs/legal/` except
`signoff.jsonl`: editing any of them after signing makes the sign-off stale. Tier `internal` needs
no sign-off; an unset tier fails; `public` needs `register.md`, `licences.md`, `privacy.md` and
`name.md` present before it can be signed, `commercial` and `client` also `terms.md`. An open `- [ ] LAWYER:` line in `docs/legal/register.md` needs
`--role lawyer`, or the owner's `--accept-risk`.

For an app whose own repo is public, `install.sh --legal-in-hq <app>` keeps the pack in the Foundry
HQ (`audits/<app>/legal/`) and makes `docs/legal` a git-ignored link to it. The gate reads through
the link and the hash is unchanged by the move. A fresh clone or a git worktree has no link: run
the gate from the main checkout, and `install.sh --update` puts a missing link back.

## What stays with the owner
Every legal and tax sign-off. 
GitHub branch protection (require CI + review before merge), enabling the GitHub connector,
adding repo secrets, activating the git hook, and approving any gitleaks allowlist entry.
