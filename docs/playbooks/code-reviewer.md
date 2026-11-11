---
role: code-reviewer
last-reviewed: 2026-10-14
status: current
---

# Playbook: code-reviewer

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
Independent read-only review: correctness, concurrency, errors

## Current practices
- Lint and type findings are compared only at a pinned tool version. A linter bump is its own commit that re-baselines the ratchet, never part of a feature PR. A reviewer who sees a ratchet delta checks first whether the tool version changed.

## Watch list
review checklists, common bug classes per stack, static-analysis tooling

## Change log
- 2026-10-10: seeded (baseline).
- 2026-10-14: current practices added from `radar/reports/2026-10-14-build.md` (owner accepted all proposed edits).
