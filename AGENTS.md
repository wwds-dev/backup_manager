# AGENTS.md: engineering process

This app is built the Foundry way: roles, gates, written artifacts. This file is the short form
and is Foundry-owned (`install.sh --update` overwrites it): never put app facts here. App facts
live in `docs/foundry/app-context.md`; product facts in the README. Any workspace-level rules
above this repo still apply.

**At session start:** read `docs/foundry/app-context.md` (its invariants override defaults), then
say which phase this session's work belongs to. **Before starting a phase,** read that phase's
part of `docs/foundry/PROCESS.md`, the full reference. Do not load it whole for a small task.

## One session owns a spec
Before Define or Build for a change, run `python3 docs/foundry/tooling/session_start.py --inflight`
(the session-start line shows it too). It lists specs not yet released, unmerged `claude/*`
branches and other worktrees. If one matches your change, stop and tell the owner; do not build.
Otherwise name the spec slug as yours. A session started by another session starts no further
sessions: it proposes them to the owner. No session exists only to relay another's status; read
the files or ask the owner.

## Owner
The owner is the CEO and the only approver. Agents advise, build and review; they do not approve
their own work. A **legal sign-off** (owner or a lawyer) and a **tax sign-off** (owner or an
accountant) are never an agent's. For a `client` app the client accepts the quote, each spec, each
change and the delivery; the owner still approves every gate.

## Distribution tier
`## Distribution` in app-context names one tier. An app with no tier is `unclassified`: Release
stops until it is set.

| Tier | Meaning | Case | Legal | Launch | Support | Legal sign-off |
|---|---|---|---|---|---|---|
| `internal` | runs only on the owner's machines | no | register and licence inventory | no | no | none |
| `public` | free; public repo or download | no | plus LICENSE, notices, disclaimers, privacy note, name check | optional | `SUPPORT.md`, security contact | owner |
| `commercial` | paid | yes | full pack | yes | yes | owner; a lawyer while a lawyer trigger is open |
| `client` | built to order for a named client | quote and SOW, accepted by the client | contract pack and DPA | no | handover and warranty | owner; a lawyer for the contract templates (first use) and triggers |

Only the owner sets the tier; raising it goes through Comply first. An agent may propose one by
adding `Status: proposed by agent, not yet confirmed by the owner` under `tier:`. Release stays
stopped while that line is there, and an agent never deletes it.

## The pipeline
Every change that is more than a typo goes through these phases. Each ends in a file under
`docs/` (or the PR). **GATE** stops until the owner approves; **CLIENT** also needs the client.

| # | Phase | Role | Output | Gate |
|---|---|---|---|---|
| 0 | Case (`commercial`, `client`) | `business-finance` | `docs/business/case.md`; client: `docs/engagement/quote.md`, `sow.md` | GATE, CLIENT |
| 1 | Define | `product-manager` | `docs/specs/<slug>.md` | GATE if user-visible or new; CLIENT |
| 2 | Design (user-facing only) | `ux-designer` | section in the spec | |
| 3 | Architect | `architect` | section in the spec; `docs/adr/NNNN-*.md` | GATE if state, concurrency or boundaries |
| 4 | Plan | orchestrator | backlog tasks, milestone and estimate (`plan.py`) | |
| 5 | Build | `engineer` | branch, tests first or alongside, small commits | client: `order.py gate` first |
| 6 | Review | `code-reviewer` | read-only, a different agent from the author | |
| 7 | Verify | `qa-engineer` | test plan, mutation check, suite in every mode | |
| 8 | Secure | `security-engineer` | required for network, secrets, auth, untrusted input, file writes, packaging | |
| 9 | Document | `tech-writer` | README, user docs, CHANGELOG | |
| 10 | Comply | `legal-compliance` | `docs/legal/`, `docs/audit/<slug>-legal-compliance.md` | GATE: sign-off |
| 11 | Launch (per tier) | `marketing`, `customer-support` | `docs/launch/<version>.md`, `SUPPORT.md` | |
| 12 | Release | `sre-release` | build, sign, install, smoke test | GATE; CLIENT |
| 13 | Operate | support, release, product | triage, incidents, 30-day review | |

Skip phases only for typos, comment fixes, test-only changes, dependency-free refactors with
unchanged behaviour, and phases the tier table marks "no". Say which were skipped and why.

## Always (full text in PROCESS.md under the same names)
- **Client delivery.** The order lives in the Foundry HQ (`orders/<id>.toml`), never here. Agents
  never contact the client, send, chase, invoice, charge or accept a contract. No Build before
  `python3 tools/order.py gate <id> build --spec <slug>` passes in the HQ. A client's acceptance is
  recorded, never inferred.
- **Legal sign-off.** Agents prepare and check; a person signs. Never run `legal_gate.py sign`,
  never edit `docs/legal/signoff.jsonl`, never write "compliant", "approved" or "legally
  reviewed". `python3 docs/foundry/tooling/legal_gate.py check .` decides whether Release may
  start. Lawyer triggers are open `- [ ] LAWYER:` lines in `docs/legal/register.md`. Never
  `git add -f` anything under `docs/legal`.
- **Legal consults** and the optional **Domain specialist** review at Define, Architect and Review,
  read-only; their P0/P1 findings count like a reviewer's.
- **Local models** draft, never decide (`docs/foundry/tooling/local_model.py`, loopback only, no
  cloud fallback). Never local: gate decisions, review, QA verdicts, security, legal, architecture.
- **Radar check.** `/radar-check <scope>` at Define, before Architect, Secure, Comply, Launch and
  Release, and on any upgrade. It proposes only.
- **Log activity** at the start and end of each phase:
  `python3 docs/foundry/tooling/log_activity.py . <phase> start|done [--spec <slug>]`.
- **Record approvals** right after the owner's explicit yes, quoting their words:
  `python3 docs/foundry/tooling/record_approval.py . <gate> --spec <slug> --words "<...>"`. Never
  from silence, never in a later session, never for `comply`.
- **Time.** Agent time is measured by the HQ. The owner's hours: `log_hours.py . <hours>`.

## Definition of done
- The success measure is demonstrably met (a test, a number, or a screenshot).
- Full suite green in every mode; new logic mutation-checked.
- Reviewer P0/P1 findings fixed or explicitly deferred by the owner.
- CHANGELOG entry; docs updated; version bumped per the app's versioning doc.
- CI green and the tooling baseline (`docs/foundry/tooling-baseline.md`) has not regressed.
- `legal_gate.py check` passes for the tier; every public claim is on the checked claims list.
- `public`, `commercial`: `SUPPORT.md` and a private security contact exist. `client`:
  `order.py gate <id> done` passes in the HQ.
- An app that calls a model: unit tests use fakes or fixtures; the live eval ran on the cheapest
  adequate model, its cost recorded (`model_use.py --purpose eval`).

## Rules for agents
- **Write to files, not chat.** A finding that is not in a file did not happen.
- **Reviewers and QA are read-only**; they report, they do not fix.
- **Evidence over assertion.** Cite file:line, a command and its output, or a measured number.
  Say "not verified" when it was not run.
- **Never weaken a test to get green.** Fix the code or raise it.
- **No agent is a lawyer, accountant or regulator.** Flag what needs a qualified person; cite the
  rule, its source and date; never give a legal or tax opinion or record a sign-off.
- Concurrent sessions may share this worktree: stage files by name, never `git add -A`.
- Do not commit, push, or release without the owner asking.
- Playbooks (`docs/playbooks/<role>.md`) are Foundry's copies: never hand-edit them in an app.
  `status: baseline` or `last-reviewed` over 90 days old means stale: say so.

## Where things live
`docs/specs/` · `docs/adr/` · `docs/audit/` · `docs/legal/` · `docs/business/` · `docs/launch/` ·
`docs/support/` · `docs/playbooks/` · `docs/engagement/` (client apps) · `docs/foundry/`:
`app-context.md`, `PROCESS.md`, `plan.toml`, `approvals.jsonl`, `activity.jsonl`, `time.jsonl`,
`model_use.jsonl`, `tooling/`. Agents in `.claude/agents/`; commands `/ship-feature`, `/audit`,
`/legal-check`, `/harden`, `/radar-check` in `.claude/commands/`. Machine-checked gates
(`/harden`: CI, lint, coverage, secret and dependency scanning) decide whether a build fails.
