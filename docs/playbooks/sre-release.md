---
role: sre-release
last-reviewed: 2026-10-14
status: current
---

# Playbook: sre-release

Canonical copy lives in the Foundry repo; apps receive it via `install.sh --update`.
Changes come from `radar/reports/` and need owner approval.

## Scope
Build, packaging, CI, signing, smoke tests, monitoring, runbooks

## Current practices
- CI uses the current major of every first-party action (checkout, setup-python, setup-node, upload-artifact), and the release check fails if any job log carries a GitHub deprecation annotation. Dependabot's `github-actions` ecosystem is enabled so action majors are proposed automatically.
- CI pins runner images by version (`ubuntu-24.04`, `macos-26`) instead of `-latest`, and moves to a new image deliberately, as one reviewed change per app, when GitHub announces a `-latest` migration. Python is pinned to a minor version (`"3.11"`), never to a patch. Record in app-context which macOS the CI tests compared with the one users run.
- A Qt/PySide6 minor upgrade is its own change per app: read the PySide changelog, upgrade on a branch, run the suite and `main.py --selftest` against a **packaged** build, and keep platform workarounds (`appkit_guard`) until a packaged run without them proves the fix. Prefer Qt LTS releases (6.12) as upgrade targets.
- PyInstaller macOS builds are `--onedir --windowed` `.app` bundles, never `--onefile` (blocked in PyInstaller 7), never built with `sudo`.
- Release notes state the signing level of every bundle (ad-hoc / Developer ID / notarized). Distribution outside this Mac waits for Developer ID plus notarization (see security-engineer playbook).

## Watch list
packaging tools, platform signing and service-manager changes, CI platform changes, observability practice
PySide6/Qt (https://code.qt.io/cgit/pyside/pyside-setup.git/tree/doc/changelogs), PyInstaller (https://pyinstaller.org/en/stable/CHANGES.html)

## Change log
- 2026-10-10: seeded (baseline).
- 2026-10-14: current practices added from `radar/reports/2026-10-14-ship.md` (owner accepted all proposed edits).
