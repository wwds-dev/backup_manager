# Backup Control Center — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)

---

## v2 — current

- [x] `P1` `feature` `@ai` **Lab Health cleanup made safe for regular use.** Caches (always safe, permanent delete) are split from Envs (`.venv`, `node_modules`, `build`, `dist`: Trash only, offered after 30 idle days and only with a lockfile/manifest to rebuild from). Nothing pre-ticked, *Select all safe*, red marking plus a "Will delete" total for ticked items, rebuild command per row, tracked folders never offered. Git worktrees (`.git` as a file: `imprint-base`, `imprint-deps`) are no longer reported as "no git repo". Tests in `tests/test_lab_health.py`; installed as v2.068.
- [x] `P0` `bug` `@ai` **A background QThread could be destroyed mid-run and abort the app** ("QThread: Destroyed while thread is still running"; crash reports 2026-10-14 02:27 and 02:45, ~2 suite runs in 100). `StorageCard.refresh()` deletes the iCloud tile with its `du` worker still running, so the last reference — the bound `run` PySide holds — went on the worker thread as `run()` returned; the tile's reconnect worker and both OAuth dialogs had the same shape, and the backup webhook thread had no owner at all and aborted every time a backup finished with a webhook set. Every worker now starts through `start_thread()`, a GUI-thread keeper that holds it until `finished` (`replace_worker()` uses it too). `tests/test_thread_lifetime.py` runs each case in a child interpreter; mutation-checked; 100/100 suite runs clean.
- [x] `P0` `bug` `@ai` **Opening the menu bar menu could abort the app on macOS 27** (crash reports 2026-10-07 15:18 and 15:43: `-[NSEvent clickCount]` raising inside `NSMenuDidBeginTracking`). Qt's cocoa plugin reads `clickCount` off a non-mouse event, which macOS 27 turns into an uncatchable Objective-C exception. `appkit_guard.py` — the lab's seventh code-identical copy of `lab_hub/ui/appkit_guard.py` — answers 0 for those events and is installed in `main()` before `QApplication`. `tests/test_appkit_guard.py` proves the crash unguarded, the fix guarded, the install order, and no drift from Lab Hub's original. Verified on hardware 2026-10-14: installed v2.062, menu bar menu opened 10–20 times by the owner, no new crash report.
- [x] `P1` `bug` `@ai` **Lab Health follow-ups.** Commit selected acted on the stale `currentRow()` (it named the clean `shopfront`): it now uses the real selection, is disabled unless one dirty row is selected and names the project. Symlinked/out-of-tree projects (`altmerch_store`, `syndustryx`, 10 GB) are never ticked or cleaned, and cleanup refuses any path outside its project (`lab_health.cleanup_targets`). Checkbox column headed *Clean* with a tooltip; linked plain folders read grey. Tests in `tests/test_lab_health.py`.
- [x] `P2` `feature` `@ai` Lab Health: Commit selected button (gitleaks-gated), per-project "don't warn about missing manifest", manifest warning only for Python projects, symlinked projects resolved (`lab_health.py`, `tests/test_lab_health.py`)
- [x] `P1` `feature` `@ai` Backup pause / resume via SIGSTOP / SIGCONT
- [x] `P1` `feature` `@ai` Tray icon badge when a backup is overdue
- [x] `P2` `feature` `@ai` Restore last log scroll position on relaunch
- [x] `P2` `feature` `@ai` Per-folder last-synced timestamp in the Folders card
- [x] `P2` `feature` `@ai` Backup triggered on USB volume mount
- [x] `P1` `feature` `@ai` Backup schedule time picker in Settings
- [x] `P2` `testing` `@ai` Regression test for the overdue-notification cooldown persisted in `state.json`
- [x] `P3` `docs` `@ai` Document the `_Admin/backup/` file map in the README rather than only in the table
- [x] `P1` `bug` `@ai` **Backup history only ever showed the day's first run.** Several backups a day (manual re-runs, USB-mount triggers) append to the same daily log file, but `last_backup_info()`/`last_backup_age_hours()`/`last_sync_per_folder()` and the History dialog's `_parse_runs()` all scanned each log as one block of text — so the status shown was always the day's first run's, and the History table listed at most one row per day no matter how many runs actually happened. Fixed with `iter_log_runs()`, which splits a log into per-run blocks on the `===== Backup run started` markers; every caller now iterates runs, not files, so "Last 15 runs" in the History table means runs.
- [x] `P1` `bug` `@ai` **Closing a fullscreen window left a black macOS Space.** The app now leaves fullscreen before the animated hide-to-menu-bar transition, drops the Dock tile only after hiding, and restores a minimized window when reopened.
- [x] `P1` `bug` `@ai` **Backup pre-flight checked the destination instead of the Google Drive mount.** A missing destination is valid because the backup script creates it; Run, Dry run, quick-folder backup, and Preview deletions now test the mounted Drive root and no longer block a healthy first run.

- [x] `P2` `infra` `@ai` **Versioned `v<MAJOR>.<BUILD>`, shown in the app.** The arc
  lives in `VERSION`; the build is `git rev-list --count HEAD`, so it cannot be forgotten.
  `version.py` reads live git from a checkout and a `_build_info.json` stamped by
  `scripts/stamp_version.py` from a frozen bundle, and says `v2.???` rather than guessing
  when it has neither. Shown in the window title, and read by Lab Hub's tile so you can see which
  build its Launch button would open. Lab-wide scheme, same two inputs as the Lab Project
  Monitor.

- [x] `P1` `bug` `@ai` **Every storage tile popped out of the window as its own floating panel.**
  Two separate escapes, both of which put a real top-level window on screen.
  `StorageTile.__init__` called `setVisible(True)` on the account label *before*
  adding it to the tile's layout — a widget with no parent is a window, so each tile
  with an account line flashed one. And `StorageCard.refresh()` dropped the old tiles
  with `setParent(None)`, which turns a *visible* widget into a visible top-level
  window; Qt does not hide it for you. Any refresh with the window open (the 5-minute
  timer, network coming back, a theme change, "Refresh all") left the whole row of
  230px tiles floating over the desktop. Tiles are now hidden before the reparent and
  disposed of with `deleteLater()` — `setParent(None)` alone never freed them either,
  because each tile's own button lambdas capture the tile. `tests/test_tile_windows.py`
  checks both by behaviour.

- [x] `P1` `bug` `@ai` **"Open at login" opened a window and took the dock, every login.**
  It registered a System Events login item, and a login item cannot pass arguments, so
  the app could only start its default way. It is a LaunchAgent now
  (`com.wwds-dev.backup-control-center.login`) running `open -a … --args --background`,
  which is the mode the app already had. `--background` also sets the accessory
  activation policy before the window is built, so no dock tile is claimed on the way
  up. An existing login item is migrated on first launch and removed, since both would
  otherwise fire. `tests/test_login_agent.py`.

- [x] `P1` `infra` `@me` Rebuild and reinstall with `./build_app.sh`: v2.068 installed 2026-10-20, so the QThread keeper is in the installed app. Re-grant Full Disk Access if the backup or scans fail silently.
- [ ] `P3` `feature` `@ai` Lab Health: let the 30-day idle threshold be set in the UI, and offer `pip freeze > requirements.txt` for envs locked only for lack of a manifest (shopfront, syndustryx)
- [ ] `P3` `bug` `@ai` `replace_worker()` only disconnects a still-running scan; a `done` already queued can still land before the new result (deferred P3 in `docs/audit/qthread-lifetime-review.md`)
- [ ] `P2` `docs` `@ai` Fill in `docs/company/app-context.md`: only Invariants is written; Product, Stack, Commands, hot spots, security surface and test bar are still placeholders
- [ ] `P3` `docs` `@ai` Add a CHANGELOG: the AGENTS.md definition of done requires one and the repo has none

## v3 — blocked or deferred

- [ ] `P1` `infra` `@me` **Developer ID code signing** — needs a paid Apple Developer account ($99/yr). Removes the Full Disk Access re-grant after every rebuild and makes the launchd fallback reliable. Cannot be done in code.
- [x] `P2` `feature` `@ai` Backup verification spot-check — no Drive API needed after all: the destination is a local Google Drive folder, so `verify.py` compares it directly (honouring the excludes, `--update` and `--modify-window=2`). Tested (`tests/test_verify.py`), but library-only — see the item below.
- [ ] `P2` `feature` `@ai` **Wire `verify.py` into the app.** It has no caller today: no button, no CLI flag, nothing in `main.py` imports it. A **🔍 Verify backup** action (Google Drive Backup card or Tools & Links) or a `--verify` flag would make the spot-check actually reachable.
- [ ] `P2` `feature` `@ai` S3 / Backblaze B2 as a second destination
- [x] `P2` `feature` `@ai` Email or webhook notification on backup failure — webhook shipped (`_fire_webhook`, URL in Settings)
- [ ] `P3` `feature` `@ai` Restore helper — pick a dated log, restore what that run moved
- [x] `P3` `performance` `@ai` Storage quota trend chart — shipped as a QPainter sparkline over persisted samples; needed neither SQLite nor a chart lib
- [ ] `P3` `research` `@ai` Power Nap backup via an `SMAppService` helper daemon — unclear whether a custom daemon qualifies
- [ ] `P3` `feature` `@ai` macOS Shortcuts action that triggers `--run-backup`
