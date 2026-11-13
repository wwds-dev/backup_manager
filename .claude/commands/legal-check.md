---
description: Bring this app's legal pack up to date, show what a sign-off would cover, and stop. Agents prepare and check; the owner or a lawyer signs in a terminal.
argument-hint: [all | register | licences | privacy | terms | name | ai-act]
---

**App root:** if this repo has `docs/foundry/app-context.md`, it is the app; otherwise you are in the Foundry HQ: the first word of the arguments is a name from `apps.md` and every repo-relative path below is relative to that app.

Scope: "$ARGUMENTS" (default `all`).

1. **Tier.** Read `## Distribution` in app-context. If the tier is missing or `unclassified`,
   propose one with reasons (who can get the app, does anyone pay, whose data it touches) and
   stop until the owner sets it.
2. **Radar.** Run `/radar-check legal` (a note under 30 days old is reused).
3. **Prepare and check.** Run the `legal-compliance` agent with the app root and the scope. It
   updates the drafts in `docs/legal/` and returns its report; save that to
   `docs/audit/legal.md`. Every rule it cites carries a source and date; anything it could not
   check says "not verified".
4. **Status.** Run `python3 docs/foundry/tooling/legal_gate.py status .` and show the owner, in
   12 lines or fewer: the tier, which pack files changed since the last sign-off, P0/P1
   findings, each open `LAWYER:` trigger and why it needs a qualified person, residual risks,
   and what was not verified.
5. **Stop.** Give the owner the command to run themselves, in their own terminal:
   `python3 docs/foundry/tooling/legal_gate.py sign . --by "<name>" --role owner` (or
   `--role lawyer`; `--accept-risk "<why>"` to override an open lawyer trigger). **Do not run
   it, do not offer to run it, and do not treat "approved" in chat as a sign-off.** Any edit to
   `docs/legal/` after signing makes the sign-off stale, by design.

Do not commit or push unless the owner asked.
