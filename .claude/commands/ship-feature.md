---
description: Run a change through the Foundry pipeline (case, define, design, architect, build, review, verify, secure, document, comply, launch, release, operate), stopping at each owner gate.
argument-hint: <feature or fix, in one or two sentences>
---

**App root:** if this repo has `docs/foundry/app-context.md`, it is the app; otherwise you are in the Foundry HQ: the first word of the arguments is a name from `apps.md` (resolve its path) and every repo-relative path below is relative to that app. Tell each agent the absolute app root and have it work only there.

Run the pipeline in `AGENTS.md` for: $ARGUMENTS

Anything after ` -- reason:` is the owner's reason for sending the app back (from the dashboard's
drag-to-dispatch). Put it in the spec under `## Why again` and brief every agent with it.

Rules for you, the orchestrator:
0. Check `last-reviewed` in `docs/playbooks/` for every role this change will use. If any is
   `status: baseline` or over 90 days old, tell the owner and offer to refresh the playbooks
   (run `/industry-radar` in the Foundry repo, then `install.sh --update`); continue only if
   they say so.
0b. Run `/radar-check feature` before Define, `/radar-check stack` before Architect,
   `/radar-check security` before Secure (when required), `/radar-check legal` before Comply,
   `/radar-check launch` before Launch and `/radar-check release` before Release, as AGENTS.md
   describes. A fresh note (under 30 days) is reused. Surface any tool it recommends to the
   owner; install nothing yourself.
0c. Read the tier from `## Distribution` in app-context. If it is missing or `unclassified`,
   propose one with your reasons and stop until the owner sets it. The tier table in AGENTS.md
   decides which of Case, Launch and Operate apply; say which you skip and why.
0d. **Tier `client`** (AGENTS.md, "Client delivery"): the order is `order:` under `## Distribution`
   and lives in the Foundry HQ (`orders/<id>.toml`). Run from the HQ; if you are in the app and
   cannot read `../foundry/tools/order.py` (or the HQ the lab names), stop and ask the owner. Run
   `python3 tools/order.py show <id>` first. No agent contacts the client: every document for
   the client is a draft, and you tell the owner it is ready to send.
   - A change to a spec the client already accepted (or a new spec) is a change request first:
     `order.py change <id> new <cr> --spec <slug> --what "..."`, `business-finance` adds its
     price and date impact to `docs/engagement/changes.md`, `product-manager` updates the spec,
     then stop: the client decides, then the owner (`order.py change <id> owner <cr> accept
     --words "<their words>"`).
   - Record a client's acceptance only when the owner tells you the client accepted, quoting
     them: `order.py accept <id> spec --spec <slug> --who "<name>" --on <date> --how email
     --ref "<subject, date>" --owner-words "<owner's words>"`. Never from silence.
1. Delegate each phase to its agent (Agent tool, `subagent_type` = the agent's name). Brief
   each with the goal, the spec path and what earlier phases decided; they have no context.
1a. **Record what the owner approves.** Each time the owner says yes at a gate (Case, Define,
   Architect, Release) or to a decision, record it straight away with their words quoted:
   `python3 docs/foundry/tooling/record_approval.py . <gate> --spec <slug> --words "<their words>"`.
   Only an explicit yes in this conversation counts; never `comply` (that is `legal_gate.py sign`).
1b. **Case** (tiers `commercial` and `client`; a new app, paid offer or client order): run
   `business-finance`, then stop and show the owner the recommendation (go, smaller, no-go) and
   the file path. Do not proceed on silence. The case's build budget goes into the plan
   (`plan.py . set --estimate-hours <h> --budget-usd <n>`) only once the owner accepts it.
1c. **Plan**, after Architect is approved: add the milestone and estimate for this change with
   `plan.py . milestone "<what ships>" --due <date> --spec <slug>` (and `plan.py . set
   --estimate-hours <h>` when the owner gave or accepted one), and log `plan done`.
2. After **Define** and **Architect**, run `legal-compliance` on the spec (then on the
   architecture section) as a read-only consult, and the domain specialist if one is installed
   (`.claude/agents/domain-*.md`). Save the reports to `docs/audit/<slug>-legal-compliance.md`
   and `docs/audit/<slug>-domain-<key>.md` (append the Architect pass). Then stop and show the
   owner a 10-line summary, including their P0/P1, plus the file path. Wait for approval before
   Build. Do not proceed on silence. For tier `client`, after the owner's Define approval the
   spec goes to the client (the owner sends it); before Build run
   `python3 tools/order.py gate <id> build --spec <slug>` in the HQ and stop if it is BLOCKED.
3. Build with `engineer`. Then run `code-reviewer` and `qa-engineer` independently (in
   parallel), plus `legal-compliance` (licences of new dependencies, claims in copy) and the
   domain specialist if installed; add `security-engineer` when AGENTS.md says it is required.
   Reviewers cannot write files: save their reports to `docs/audit/<slug>-<role>.md` yourself.
4. If any P0/P1 is found, send it back to `engineer`, then repeat Review and Verify. Stop
   after 3 loops and escalate to the owner.
5. Then `tech-writer`.
6. **Comply.** Run `legal-compliance` to bring `docs/legal/` up to date and append its clearance
   to `docs/audit/<slug>-legal-compliance.md`. Run
   `python3 docs/foundry/tooling/legal_gate.py check .`. If it fails, stop: show the owner what
   changed since the last sign-off, the open lawyer triggers, the residual risks, and the exact
   `legal_gate.py sign` command. **Never run `sign` yourself, and never record a sign-off from
   something the owner said in chat**: the owner runs it in a terminal. Continue only when
   `check` passes.
7. **Launch** (when the tier needs it): `marketing` writes `docs/launch/<version>.md` and
   `customer-support` writes `SUPPORT.md` and `docs/support/plan.md`; then `legal-compliance`
   checks the claims list. If that changed anything under `docs/legal/`, `check` fails again
   and step 6 repeats. Nothing is published, posted or sent by an agent.
8. Then `sre-release` (a gate: ask before building or installing). It runs `legal_gate.py check`
   first and stops if it fails. For tier `client`, `customer-support` writes
   `docs/engagement/handover.md` from `docs/foundry/tooling/handover_template.md` (with
   `sre-release` for deployment, runbook and credentials, `legal-compliance` for the licence
   inventory and disclosures); the owner hands it over and tells you when the client accepted
   the delivery. Record it (`order.py accept <id> delivery ...`, then `order.py handover <id>
   --on <date> --warranty-days <n>`) and run `order.py gate <id> done`: Release is done only
   when it passes.
9. **Operate** is not part of this run. Add a backlog item dated 30 days after the release for
   the post-launch review (`business-finance`, `product-manager`), and say so. For a client,
   also one for the warranty end date.
9b. **Models.** Work you hand to a local model (`docs/foundry/tooling/local_model.py`, kinds in
   AGENTS.md "Local models" and `docs/playbooks/model-routing.md`) is a draft: the same agent
   checks and the same gates apply. Never route a gate, review, QA, security or legal finding,
   or an architecture decision to a local model. If the change adds or changes a model the app
   calls, `## Models used` in app-context is updated in the same change.
10. Finish with a table: phase, agent, artifact path, result, anything skipped and why. Do not
   commit or push unless the owner asked.
