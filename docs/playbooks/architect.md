---
role: architect
last-reviewed: 2026-10-14
status: current
---

# Playbook: architect

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
Module boundaries, concurrency, state, ADRs

## Current practices
- GUI apps share one Qt line: the current LTS (6.12). A move to a non-LTS Qt needs an ADR naming the feature it buys.
- Concurrency designs assume the GIL build of CPython. Free-threaded CPython is not a target until every native dependency (PySide6 first) ships free-threaded wheels, and adopting it needs an ADR. Do not `lazy import` PySide6 or any module with import-time side effects (Qt plugins and resources, `appkit_guard`).

## Watch list
language concurrency models, persistence patterns, ADR practice

## Change log
- 2026-10-10: seeded (baseline).
- 2026-10-14: current practices added from `radar/reports/2026-10-14-build.md` (owner accepted all proposed edits).
