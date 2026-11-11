# AGENTS.md: engineering process

This app is built the Foundry way: roles, gates, written artifacts. App facts
live in `docs/foundry/app-context.md`; product facts in the README. Any workspace-level
rules above this repo still apply.

## Owner
The owner is the CEO and the only approver. Agents advise, build and review; they do not
approve their own work. Two approvals are never an agent's: a **legal sign-off** (the owner or
a lawyer) and a **tax sign-off** (the owner or an accountant). For a `client` app the client
accepts the quote, each spec, each change and the delivery (below, "Client delivery"); the owner
still approves every gate.

## Distribution tier
`## Distribution` in app-context names one tier. It decides which business departments apply.
An app with no tier is `unclassified`: the dashboard warns and Release stops until it is set.

| Tier | Meaning | Case | Legal | Launch | Support | Legal sign-off |
|---|---|---|---|---|---|---|
| `internal` | runs only on the owner's machines | no | register and licence inventory | no | no | none |
| `public` | free; public repo or download | no | plus LICENSE, notices, disclaimers, privacy note, name check | optional | `SUPPORT.md`, security contact | owner |
| `commercial` | paid | yes | full pack | yes | yes | owner; a lawyer while a lawyer trigger is open |
| `client` | built to order for a named client | quote and SOW, accepted by the client | contract pack and DPA | no | handover and warranty | owner; a lawyer for the contract templates (first use) and triggers |

Raising the tier (for example `internal` to `public`) is itself a change: it goes through
Comply before the first release at the new tier.

Only the owner sets the tier. An agent may propose one, with its evidence, by adding the line
`Status: proposed by agent, not yet confirmed by the owner` under `tier:`. While that line is
there the tier is shown but Release stays stopped; the owner confirms by deleting it (or changes
the tier first). An agent never deletes it.

## The pipeline
Every change that is more than a typo goes through these phases. Each ends in a file under
`docs/` (or the PR) and, where marked **GATE**, stops until the owner approves.

0. **Case** (`business-finance`; new app, new paid offer or client order; tiers `commercial`
   and `client`) -> `docs/business/case.md`: who pays, price, cost per unit, build budget, what
   would make it not worth doing. For a client: `docs/engagement/quote.md` and the statement of
   work draft `docs/engagement/sow.md`. **GATE**: go or no-go; for a client also **CLIENT GATE**:
   the client accepts the quote and SOW (the owner sends them; no agent does).
1. **Define** (`product-manager`) -> `docs/specs/<slug>.md`: problem, user, success measure,
   non-goals. **GATE** for anything user-visible or new. For a client: then **CLIENT GATE**, the
   client accepts the spec as written (without its Design and Architecture sections).
2. **Design** (`ux-designer`, user-facing changes only) -> section in the spec.
3. **Architect** (`architect`) -> section in the spec; `docs/adr/NNNN-*.md` for decisions
   that are expensive to reverse. **GATE** if it touches state, concurrency, or module
   boundaries.
4. **Plan** -> tasks in the backlog with priority, category and owner, and a milestone for the
   change (due date, the spec it delivers) plus the estimate in `docs/foundry/plan.toml`:
   `python3 docs/foundry/tooling/plan.py . milestone "<what ships>" --due YYYY-MM-DD --spec <slug>`
   and `plan.py . set --estimate-hours <h>`. An estimate nobody made stays unset: never fill in a
   default.
5. **Build** (`engineer`) on a branch, tests first or alongside, small commits.
6. **Review** (`code-reviewer`): a different agent from the author, read-only.
7. **Verify** (`qa-engineer`): test plan against the success measure, mutation-check new
   logic, run the suite in every mode app-context lists.
8. **Secure** (`security-engineer`): required when a change touches network, secrets, auth,
   untrusted input, file writes, or packaging.
9. **Document** (`tech-writer`): README, user docs, CHANGELOG.
10. **Comply** (`legal-compliance`) -> the legal pack in `docs/legal/` brought up to date and
    a clearance report `docs/audit/<slug>-legal-compliance.md`. **GATE: sign-off** (below).
11. **Launch** (`marketing`, `customer-support`; tiers per the table) ->
    `docs/launch/<version>.md` (positioning, listing copy, claims list, announcement plan) and
    `SUPPORT.md` / `docs/support/plan.md` (channel, response targets, known issues, refunds).
12. **Release** (`sre-release`): build, sign, install, smoke test. **GATE**. For a client also
    the handover checklist `docs/engagement/handover.md` (below), and **CLIENT GATE**: Release
    counts as done only once the client has accepted the delivery.
13. **Operate** (`customer-support`, `sre-release`, `product-manager`) -> feedback triaged into
    the backlog, incidents written up in `docs/support/incidents/`, and 30 days after a release
    `docs/business/review-<version>.md`: the success measure and the business case, measured.
    Retiring an app is a change too: user notice, data deletion, legal register closed.
    For a client: the warranty window (from the order's handover date to its end) is tracked
    here; a defect reported in it is triaged against what the warranty covers.

**Client delivery (tier `client`).** The order lives in the Foundry HQ, not in this repo:
`orders/<id>.toml`, private, written by `tools/order.py` (this repo may be handed to the client).
`## Distribution` in app-context names it (`order: <id>`). Run client work from the HQ.
- **Client gates** are recorded acts of the client, separate from the owner's approvals: the
  client accepts the quote and SOW, each spec (after Define), each change request, and the
  delivery. Each is recorded with who at the client, when, how (email, signature, meeting, call)
  and the reference: `python3 tools/order.py accept <id> quote|spec|delivery|change ...`, by the
  owner in a terminal or by the orchestrator quoting the owner's statement that the client
  accepted (`--owner-words`). Never inferred from silence or from earlier messages.
- **Agents never contact the client.** Every client-facing document (quote, SOW, spec, change
  impact, handover, invoice) is a draft the owner sends. No agent sends, chases, invoices,
  charges or accepts a contract.
- **Change requests.** After the client accepted a spec, any change to it (or a new spec) is a
  change request: `order.py change <id> new <cr> --spec <slug> --what ... [--price-eur N] [--due D]`.
  `business-finance` drafts its price and date impact in `docs/engagement/changes.md`; the
  product manager updates the spec; then the client and the owner each decide (client first,
  so the client accepts the spec as changed). When both accept, the order's price and date move
  and the plan gets a milestone.
- **Before Build**, the orchestrator runs `python3 tools/order.py gate <id> build --spec <slug>`
  in the HQ. It refuses when the quote or the spec is not accepted, when the spec changed after
  the client accepted it, or when a change request for it is not accepted by both. No build
  without it passing.
- **Handover** at Release: `docs/engagement/handover.md` from
  `docs/foundry/tooling/handover_template.md` (source and licence inventory, credentials the
  client must own, deployment and runbook, data-processing and AI-use disclosures, support
  contact, what the warranty covers and until when). Every line ticked `- [x]` or marked
  `- [~] n/a: <reason>`. Then `order.py handover <id> --on D --warranty-days N`, and
  `order.py gate <id> done` must pass: delivery accepted, checklist closed, dates recorded.
- **Money** is records only, in the order: quote, invoices (draft, sent, paid, with dates).
- **Contract pack** `docs/legal/client/` (services agreement, SOW, DPA, acceptance and
  warranty terms), drafted by `legal-compliance` as DRAFT. Until a lawyer has signed the app's
  pack once, the gate treats the templates as an open lawyer trigger.

**Local models.** A local model (LM Studio's server on this machine) may draft; it never
decides. `python3 docs/foundry/tooling/local_model.py --model <id> --prompt "..."` calls only a
loopback address, fails closed when the server is off (no cloud fallback) and counts every call
in `docs/foundry/model_use.jsonl` at zero cost. Backlog items it drafts carry the owner tag
`@local`, and its output is accepted only after the same checks as any other work.
- May go local: mechanical drafts a gate checks anyway (changelog and docstring drafts, test
  scaffolds, data fixtures, renames), material with client or personal data that must not leave
  the machine (summaries, redaction, classification), cheap first passes a stronger model or a
  person then reviews.
- Never local: a gate decision, code review, QA verdicts, security findings, legal findings,
  architecture decisions, and anything a person signs.
- Which model for which kind of work: `docs/playbooks/model-routing.md`. Every model the app
  itself calls is listed in app-context's `## Models used`.

**Legal consults.** Besides Comply, `legal-compliance` reviews three times, read-only, like a
domain specialist: at **Define** (which regimes the change touches: personal data, consumers,
AI, licences, the name), at **Architect** (data map, processors, retention, DPIA screening) and
at **Review** (licences of new dependencies, claims in copy, notices), each into
`docs/audit/<slug>-legal-compliance.md`. Its P0/P1 findings count like a reviewer's.

**Legal sign-off.** Agents prepare and check; they never approve. A legal document is `DRAFT`,
then `CHECKED (agent)`, and only a person makes it `SIGNED OFF`:
- `python3 docs/foundry/tooling/legal_gate.py check .` decides whether Release may start. It
  fails when the tier is unset, the pack is missing, there is no sign-off, the pack changed
  after the sign-off, or a lawyer trigger is open and only the owner signed without accepting
  the risk in writing.
- `python3 docs/foundry/tooling/legal_gate.py sign . --by "<name>" --role owner|lawyer` records
  a sign-off against a hash of `docs/legal/`. **A person runs it in a terminal. Agents never
  run `sign`**, never edit `docs/legal/signoff.jsonl`, and never write "compliant", "approved"
  or "legally reviewed" anywhere.
- **Lawyer triggers** (an open `- [ ] LAWYER:` line in `docs/legal/register.md`): a possibly
  high-risk AI Act classification; special-category or children's data; regulated finance,
  insurance, health or gambling activity; a DPIA with high residual risk; the first commercial
  terms and the client contract templates; a trademark conflict or filing. The owner may
  override one only with `--accept-risk "<why>"`, which is recorded.
- **Public repo.** When this app's own repository is public, the pack is kept in the Foundry HQ
  (`audits/<app>/legal/`, private) and `docs/legal` here is a git-ignored link to it, so the
  register of open risks and the sign-offs are never published. Work through `docs/legal/` as
  usual, from the main checkout (a git worktree has no link). What users must see (privacy note,
  terms, notices, `LICENSE`) is published by copying the signed text into the README, the app
  or the listing through the pipeline. Never `git add -f` anything under `docs/legal`.
- Tax follows the same rule without the tool: `business-finance` prepares, the owner or an
  accountant signs the `## Sign-off` section of `docs/business/case.md`.

**Domain specialist (optional).** When `.claude/agents/domain-<key>.md` is installed (a
read-only reviewer for a regulated or expert domain, briefed by the `## Domain specialist`
section of app-context), it reviews three times: at **Define**, the spec before its gate; at
**Architect**, the architecture section before its gate (both into
`docs/audit/<slug>-domain-<key>.md`); at **Review**, the diff, in parallel with
`code-reviewer`. Its P0/P1 findings count like a reviewer's. The domain specialist covers the
product's subject matter; `legal-compliance` covers the owner's duties as publisher and seller,
owns the legal register, and takes the specialist's findings into it.

Skip phases only for: typos, comment fixes, test-only changes, dependency-free refactors with
unchanged behaviour, and the phases the tier table marks "no". Say which phases were skipped
and why. Comply is skipped only when the change adds no dependency, data flow, user-facing
copy, model use or distribution channel: say so in the summary.

**Radar check.** Run `/radar-check <scope>` so the work uses the best available tooling and
practice: at **Define** for a new app, idea or feature (`new-idea` / `feature`); before
**Architect** (`stack`); before **Secure** (`security`); on any dependency or version
**upgrade** (`upgrade`); before **Comply** (`legal`); before **Launch** (`launch`); before
**Release** (`release`). Moving between other phases reuses the latest note (under 30 days
old). It proposes only: nothing is installed, enabled or connected without the owner's yes.

**Log activity.** At the start and end of each phase, run
`python3 docs/foundry/tooling/log_activity.py . <phase> start|done [--spec <slug>]` (phases:
case define design architect plan build review verify secure document comply launch release
operate; use `blocked` when stopped on a gate). The Foundry workspace reads it, live, to show
what is in progress. It records nothing else and never blocks work: if the command fails, say
so and continue.

**Record approvals.** When the owner approves a gate (Case, Define, Architect, Release, or a
decision), the orchestrator records it right after the owner's explicit yes in that same
conversation, quoting their words:
`python3 docs/foundry/tooling/record_approval.py . <gate> --spec <slug> --words "<what they said>"`.
Never from silence, never inferred from earlier work, never on the owner's behalf in a later
session. It refuses `comply`: the legal sign-off is only `legal_gate.py sign`, run by a person.
The workspace shows each gate as approved (who, when, the words) or "approval not recorded".

**Time.** Agent time and model use are measured from Claude Code's session transcripts by the
Foundry HQ; nothing to record. The owner's own hours are a manual entry:
`python3 docs/foundry/tooling/log_hours.py . <hours> [--note TEXT]`, run by the owner or by an
agent typing the number the owner gave.

## Definition of done
- The success measure is demonstrably met (a test, a number, or a screenshot).
- Full suite green in every mode; new logic mutation-checked.
- Reviewer P0/P1 findings fixed or explicitly deferred by the owner.
- CHANGELOG entry; docs updated; version bumped per the app's versioning doc.
- CI is green and the tooling baseline (`docs/foundry/tooling-baseline.md`, from `/harden`) has not
  regressed: no new lint/type findings, coverage at or above the floor, no secrets, no new
  vulnerable dependency.
- `legal_gate.py check` passes for the app's tier, and every claim in release notes, listing
  and landing copy is on the checked claims list.
- For `public` and `commercial`: `SUPPORT.md` and a private security contact (`SECURITY.md`,
  a `security.txt` or a security section in `SUPPORT.md`) exist; for `commercial` the support
  channel is live and answered (the Foundry workspace warns P1 when either file is missing).
- For `client`: the client accepted the delivery, the handover checklist is closed and the
  warranty end is recorded (`order.py gate <id> done` passes in the HQ).
- An app that calls a model: unit tests use fakes or recorded fixtures, never a live model; the
  live eval suite ran on the cheapest adequate model within the plan's eval budget, its cost
  recorded (`model_use.py --purpose eval`).

## Rules for agents
- **Write to files, not chat.** A finding that is not in a file did not happen.
- **Reviewers and QA are read-only**; they report, they do not fix.
- **Evidence over assertion.** Cite file:line, a command and its output, or a measured
  number. Say "not verified" when it was not run.
- **Never weaken a test to get green.** Fix the code or raise it.
- **No agent is a lawyer, accountant or regulator.** Flag what needs a qualified person; cite
  the rule, its source and date; never give a legal or tax opinion or record a sign-off.
- Concurrent sessions may share this worktree: stage files by name, never `git add -A`.
- Do not commit, push, or release without the owner asking.
- Read `docs/foundry/app-context.md` first; app-specific invariants there override defaults.

## Staying current
- Every agent reads `docs/playbooks/<role>.md`. Playbooks are copies of Foundry's
  current practice, refreshed with `install.sh --update`; never hand-edit them in an app.
  `status: baseline` or `last-reviewed` over 90 days old means stale: say so. A baseline
  legal, tax or marketing-law practice is a prompt to check the source, not a fact.
- Foundry's radar proposes playbook changes; only the owner approves them.

## Machine-checked gates
`/harden <app>` wires CI, lint, coverage, secret and dependency scanning into an app (see
`docs/foundry/tooling/README.md`). These checks, not an agent's opinion, decide whether a build
fails. `legal_gate.py check` is the same kind of gate for the legal sign-off. What stays with
the owner: branch protection, repo secrets, the GitHub connector, activating the git hook, and
every sign-off.

## Where things live
`docs/specs/` specs · `docs/adr/` decisions · `docs/audit/` review reports ·
`docs/legal/` legal pack and `signoff.jsonl` · `docs/business/` case, pricing, reviews ·
`docs/launch/` launch plans · `docs/support/` support plan, FAQ, incidents ·
`docs/playbooks/` role practices · `docs/foundry/app-context.md` this app's facts ·
`docs/foundry/plan.toml` estimates and milestones · `docs/foundry/approvals.jsonl` gate
approvals · `docs/foundry/activity.jsonl` phase log · `docs/foundry/time.jsonl` owner hours ·
`docs/foundry/model_use.jsonl` model runs (local and eval) · `docs/engagement/` quote, SOW,
change impacts, handover (client apps; the order itself is in the Foundry HQ).
Agents in `.claude/agents/`; commands `/ship-feature`, `/audit`, `/legal-check`, `/harden`,
`/radar-check` in `.claude/commands/`.
