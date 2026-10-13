---
role: security-engineer
last-reviewed: 2026-10-10
status: baseline   # baseline = seeded, not yet verified by a radar run; becomes current after first approved review
---

# Playbook: security-engineer

Canonical copy lives in the company repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
Secrets, network surfaces, untrusted input, dependencies, packaging

## Current practices
_Baseline: the rules in `AGENTS.md` and the agent prompt. The first radar run fills this in._

## Watch list
OWASP (incl. LLM Top 10), CVEs in app dependencies, platform signing/notarization, secret handling

## Change log
- 2026-10-10: seeded (baseline).
