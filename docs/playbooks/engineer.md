---
role: engineer
last-reviewed: 2026-10-14
status: current
---

# Playbook: engineer

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
Implementation with tests alongside code

## Current practices
- New apps target the newest CPython branch in *bugfix* status (3.14 as of 2026-10). An app on a *security-only* branch schedules its move at least 12 months before that branch's EOL: 3.11 reaches EOL in 2027-10, so the move goes in the backlog now. The move is its own change: rebuild the venv with uv, re-run `install_app.sh` (the launcher links that minor version's libpython), and run the full suite and `--selftest`.
- Track the current Qt LTS (6.12 from 2026-10). Upgrade PySide6 in one app first. Run its `--selftest`, and open every tray and menu-bar menu on the current macOS **with `appkit_guard` disabled**. Only then roll the upgrade out, and only then delete the guard copies. Pin the PySide6 version in requirements instead of leaving it unpinned.
- Pin model-provider SDKs (anthropic, openai, google-genai). Read the changelog before each bump. Treat a major-version gap as a planned task with its own tests, not a drive-by upgrade.

## Watch list
language/framework releases and deprecations, lint/type tooling, packaging, AI-assisted coding practice

## Change log
- 2026-10-10: seeded (baseline).
- 2026-10-14: current practices added from `radar/reports/2026-10-14-build.md` (owner accepted all proposed edits).
