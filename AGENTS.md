# AGENTS.md: engineering process

This app is built the Foundry way: roles, gates, written artifacts. App facts
live in `docs/company/app-context.md`; product facts in the README. Any workspace-level
rules above this repo still apply.

## Owner
The owner is the CEO and the only approver. Agents advise, build and review; they do not
approve their own work.

## The pipeline
Every change that is more than a typo goes through these phases. Each ends in a file under
`docs/` (or the PR) and, where marked **GATE**, stops until the owner approves.

1. **Define** (`product-manager`) -> `docs/specs/<slug>.md`: problem, user, success measure,
   non-goals. **GATE** for anything user-visible or new.
2. **Design** (`ux-designer`, user-facing changes only) -> section in the spec.
3. **Architect** (`architect`) -> section in the spec; `docs/adr/NNNN-*.md` for decisions
   that are expensive to reverse. **GATE** if it touches state, concurrency, or module
   boundaries.
4. **Plan** -> tasks in the backlog with priority, category and owner.
5. **Build** (`engineer`) on a branch, tests first or alongside, small commits.
6. **Review** (`code-reviewer`): a different agent from the author, read-only.
7. **Verify** (`qa-engineer`): test plan against the success measure, mutation-check new
   logic, run the suite in every mode app-context lists.
8. **Secure** (`security-engineer`): required when a change touches network, secrets, auth,
   untrusted input, file writes, or packaging.
9. **Document** (`tech-writer`): README, user docs, CHANGELOG.
10. **Release** (`sre-release`): build, sign, install, smoke test. **GATE**.

**Domain specialist (optional).** When `.claude/agents/domain-<key>.md` is installed (a
read-only reviewer for a regulated or expert domain, briefed by the `## Domain specialist`
section of app-context), it reviews three times: at **Define**, the spec before its gate; at
**Architect**, the architecture section before its gate (both into
`docs/audit/<slug>-domain-<key>.md`); at **Review**, the diff, in parallel with
`code-reviewer`. Its P0/P1 findings count like a reviewer's.

Skip phases only for: typos, comment fixes, test-only changes, dependency-free refactors with
unchanged behaviour. Say which phases were skipped and why.

**Radar check.** Run `/radar-check <scope>` so the work uses the best available tooling and
practice: at **Define** for a new app, idea or feature (`new-idea` / `feature`); before
**Architect** (`stack`); before **Secure** (`security`); on any dependency or version
**upgrade** (`upgrade`); before **Release** (`release`). Moving between other phases reuses the
latest note (under 30 days old). It proposes only: nothing is installed, enabled or connected
without the owner's yes.

**Log activity.** At the start and end of each phase, run
`python3 docs/company/tooling/log_activity.py . <phase> start|done [--spec <slug>]` (phases:
define design architect build review verify secure document release; use `blocked` when stopped
on a gate). The Foundry dashboard reads it to show what is in progress. It records nothing else
and never blocks work: if the command fails, say so and continue.

## Definition of done
- The success measure is demonstrably met (a test, a number, or a screenshot).
- Full suite green in every mode; new logic mutation-checked.
- Reviewer P0/P1 findings fixed or explicitly deferred by the owner.
- CHANGELOG entry; docs updated; version bumped per the app's versioning doc.
- CI is green and the tooling baseline (`docs/company/tooling-baseline.md`, from `/harden`) has not
  regressed: no new lint/type findings, coverage at or above the floor, no secrets, no new
  vulnerable dependency.

## Rules for agents
- **Write to files, not chat.** A finding that is not in a file did not happen.
- **Reviewers and QA are read-only**; they report, they do not fix.
- **Evidence over assertion.** Cite file:line, a command and its output, or a measured
  number. Say "not verified" when it was not run.
- **Never weaken a test to get green.** Fix the code or raise it.
- Concurrent sessions may share this worktree: stage files by name, never `git add -A`.
- Do not commit, push, or release without the owner asking.
- Read `docs/company/app-context.md` first; app-specific invariants there override defaults.

## Staying current
- Every agent reads `docs/playbooks/<role>.md`. Playbooks are copies of the company's
  current practice, refreshed with `install.sh --update`; never hand-edit them in an app.
  `status: baseline` or `last-reviewed` over 90 days old means stale: say so.
- The company's radar proposes playbook changes; only the owner approves them.

## Machine-checked gates
`/harden <app>` wires CI, lint, coverage, secret and dependency scanning into an app (see
`docs/company/tooling/README.md`). These checks, not an agent's opinion, decide whether a build
fails. What stays with the owner: branch protection, repo secrets, the GitHub connector, and
activating the git hook.

## Where things live
`docs/specs/` specs · `docs/adr/` decisions · `docs/audit/` review reports ·
`docs/playbooks/` role practices · `docs/company/app-context.md` this app's facts.
Agents in `.claude/agents/`; commands `/ship-feature`, `/audit` in `.claude/commands/`.
