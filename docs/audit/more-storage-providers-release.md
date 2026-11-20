# Release note: more-storage-providers (Foundry phase 12), 2026-11-20

Tier `public`. Owner approved the Release gate in chat ("Approve release"), recorded in `docs/foundry/approvals.jsonl`.

## What shipped
- Built from `main` at **4eb8d7d** (docs-only difference from the tested 6b9ef8f; `git diff 6b9ef8f..4eb8d7d` touches only `docs/`). Installed to `/Applications` as **v2.258** (`_build_info.json`: build 258, commit 4eb8d7d, 2026-11-20T22:50:24Z). Replaces v2.212.
- Contents: Google Drive/Photos split, Dropbox, OneDrive, Proton link-only tile, per-tile links, Secure fixes R-1 to R-3.
- Other specs whose code is on `main` and therefore in this build: folder-backup-secret-filter (Secure done), icloud-unavailable (Review and Verify pass), quota-off-ui-thread (code-reviewed), tile-used-wording (mutation-checked, no second review), sidebar-redesign (no spec file, build log only). `secrets-vault` is not in `main`. All five were already installed in earlier builds (TODO.md).
- PyInstaller version was not recorded by `build_app.sh` (unpinned).

## Gate evidence
- `release_check.py .` (main checkout): "legal gate clear (tier public)", "Release may start", run before approval and again after.
- Radar: `docs/foundry/radar-notes/2026-11-20-release.md` (nothing blocking; PySide6 6.12.1 to take later).
- Tests: `HOME=<scratch>/fakehome QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` on 6b9ef8f: **525 tests, 0 failures, 0 errors, 2 skipped**; exit 139 is the known Qt teardown crash; fake home empty afterwards. Not re-run on 4eb8d7d (docs-only diff). No CI exists (`.github/workflows` absent): this local run is the evidence.

## Smoke test (app-context checklist)
| Step | Result |
|---|---|
| Installed app launches | PASS (pid up after `open`) |
| Window title shows new version | PASS: "Backup Control Center v2.258" (screenshot) |
| Overview loads | PASS: gauges, Mac disk "581.8 GB used of 926.4 GB", Google Drive 41%, Dropbox 0%, iCloud "16.0 MB local cache", jobs list |
| Lab Health scan runs | **NOT VERIFIED**: my window control was blocked (the window sits on a full-screen Space I could not reach), so I did not click it |
| Quit | PASS (SIGTERM after two AppleScript quits returned "User cancelled"; no backup was running) |
| Relaunch, `state.json` intact | PASS at file level: same four keys and size (154 B) before and after; the Settings screen was not inspected |
No new crash report was found in `~/Library/Logs/DiagnosticReports`.

## Owner still has to do
1. Click **Lab Health** in the installed v2.258 and run a scan (the one unverified smoke step).
2. Put your real name on the legal sign-off: it was recorded as `<your name>` (an unrelated `legal_gate.py sign ... --by FIRST LAST` process was also still running during this release; check it is not stuck).
3. Open items from Comply that stay open: name trigger (GoodSync) accepted as risk only; network trace behind "nothing is sent to the author" not measured; Microsoft/MSRC line in `SECURITY.md`; `disconnect()` does not revoke at the provider; Entra "any name you like" wording; `app-context.md` Invariants placeholder line unfilled; Google and OneDrive live reads never run (claims C15, C31).
4. No tag and no GitHub release were created. Nothing was pushed to `main`; this note is on branch `claude/nice-antonelli-4887e5` (the network was unreachable at the last push attempt, see below).
