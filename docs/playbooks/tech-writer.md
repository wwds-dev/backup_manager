---
role: tech-writer
last-reviewed: 2026-10-14
status: current
---

# Playbook: tech-writer

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
README, user docs, CHANGELOG, runbooks

## Current practices
- CHANGELOG.md at the repo root follows Keep a Changelog 1.1.0 adapted to the lab's `v<MAJOR>.<BUILD>` versions: an `## Unreleased` section at the top, then `## v2.340 - 2026-10-13` headings, newest first, ISO dates, entries grouped as Added / Changed / Deprecated / Removed / Fixed / Security, written for the user, not as a commit log. State that the project does not use semver.
- An app with no CHANGELOG.md gets one at its first Document phase, starting from the current version; earlier history is not back-filled. Changelog headings are checked against the format above by the docs test where one exists.

## Watch list
docs-as-code practice, changelog conventions, plain-language guidance

## Change log
- 2026-10-10: seeded (baseline).
- 2026-10-14: current practices added from `radar/reports/2026-10-14-ship.md` (owner accepted all proposed edits).
