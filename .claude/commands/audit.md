---
description: Internal audit of this app as an outside engineering firm would do it. Writes reports to docs/audit/.
argument-hint: [all | ux | architecture | code | qa | security | model | domain | ops | docs | legal | business | marketing | support]
---

**App root:** if this repo has `docs/foundry/app-context.md`, it is the app; otherwise you are in the Foundry HQ: the first argument is an app name from `apps.md`; resolve its path, tell each agent the absolute app root, and have it work only there.

Run the audit scope "$ARGUMENTS" (default `all`). Read-only on production code.
Anything after ` -- reason:` is the owner's reason for sending the app back to this department
(from the dashboard's drag-to-dispatch): it is not a scope. Quote it at the top of each report
and of `SUMMARY.md`, and have the agents check that concern first.

Spawn these agents in parallel (skip any not installed), each told to audit the whole repo
for its dimension and return findings ranked P0-P3 with file:line, scenario and fix:
`ux-designer` -> docs/audit/ux.md · `architect` -> architecture.md · `code-reviewer` ->
code-review.md · `qa-engineer` -> qa.md · `security-engineer` -> security.md (+ threat
model) · `model-validator` -> model-validation.md · each `domain-<key>` (scope `domain`) ->
domain-<key>.md · `sre-release` -> operations.md ·
`tech-writer` -> docs.md · `legal-compliance` (scope `legal`) -> legal.md ·
`business-finance` (scope `business`) -> business.md · `marketing` (scope `marketing`) ->
marketing.md · `customer-support` (scope `support`) -> support.md.

Read the tier from `## Distribution` in app-context first. Skip `business`, `marketing` and
`support` where the tier table in AGENTS.md marks them "no" (say so in `SUMMARY.md`); `legal`
runs for every tier. If the tier is missing or `unclassified`, the legal audit proposes one
with reasons and the summary leads with it.

The legal audit is the one audit that also writes outside `docs/audit/`: `legal-compliance`
creates or updates the drafts in `docs/legal/` (never `signoff.jsonl`) and reports what it
found in `docs/audit/legal.md`. It ends with `legal_gate.py status`, the open lawyer triggers
and the `sign` command for the owner; it never signs.

Agents without Write tools return their report; you save it. Then write
`docs/audit/SUMMARY.md`: every P0/P1 across reports (deduped), a top-10 fix order, and what
could not be verified. Do not fix anything.
