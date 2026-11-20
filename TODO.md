# Backup Control Center — TODO

> **Testing first (owner, 2026-11-20).** `P0` now means: needed before the owner can test this app on his own Mac, or a security must. Everything else waits until after testing, and no new feature or redesign row starts unless the owner asks for it.

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)

---

## Secrets vault (spec `docs/specs/secrets-vault.md`, approved 2026-10-21)

- [ ] `P0` `security` `@me` **Rotate every key that sat in plaintext on Google Drive.** Names only, from `sentinel/.env`, `imprint/vidforge/.env` and Imprint's and Sentinel's app data (the values were never read into any file or log): `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, `KIMI_API_KEY`, `DASHSCOPE_API_KEY`, `HIBP_API_KEY`, `VIRUSTOTAL_API_KEY`, `IPINFO_API_KEY`, `ABUSEIPDB_API_KEY`. Rotate at each provider, then update `sentinel/.env`, `imprint/vidforge/.env` and the apps' Settings. (`imprint/.env` holds only two Higgsfield endpoint URLs, not keys.)
- [ ] `P0` `security` `@me` **Sign `opaque1337@proton.me` in to the Proton Drive app**, so `backup_secrets.sh` finds its folder (it refuses the other two accounts).
- [ ] `P1` `security` `@me` **Purge the old plaintext copies:** in Terminal, `~/Documents/lab/_Admin/backup/purge_plaintext_secrets.sh` (lists), then `--apply`, then empty the Trash at drive.google.com.

## v2 — current

- [x] `P2` `testing` `@ai` **Code-level readiness audit (promises vs code).** Check every promise in the README and `docs/foundry/app-context.md` against the code (backup runs, secrets vault, verification, Lab Health cleanup, Time Machine); classify each Delivered / Narrower / Stub; findings to `docs/audit/` and this file. Own chat, Opus high, ~30–60 min. Requested 2026-11-18 after the lab-wide doc sweep. Done 2026-11-18: `docs/audit/2026-11-18-readiness-audit.md` (1 Blocker, 3 High, 4 Medium); the items below come from it. It also found the vault writing nightly since 2026-11-13, so the Proton sign-in item above looks done (owner to tick).
- [x] `P0` `security` `@ai` **Folder "Back up now" copies `.env` files to Google Drive in plaintext.** `run_single_folder()` (`main.py:2565-2594`) passes only `gdrive_backup_excludes.txt`, not `secret_name_patterns.txt` and the `*.example`/`*.sample`/`*.template` includes the script uses; the Excludes *Preview matches* has the same gap. Fix before the purge and key rotation, with a test on the rsync arguments. (Audit B1) Done 2026-11-20 (branch `claude/folder-backup-secret-filter-334e2b`, spec `docs/specs/folder-backup-secret-filter.md`): the one-folder backup and Preview matches read the filter from `backup_to_gdrive.sh` through `backup_filter.py` and refuse to run without the secret list; `tests/test_backup_filter.py`. Not yet built or installed.
- [ ] `P2` `security` `@me` **Secret names in other letter case reach Google Drive** (B1 security review P2-1, `docs/audit/folder-backup-secret-filter-security.md`): rsync matches case-sensitively, APFS does not, so `.Env` or `Prod.Env` pass both the nightly script and the folder backup (none exist today, names-only scan). Write `_Admin/backup/secret_name_patterns.txt` with character classes (`.[eE][nN][vV]` …), and in `backup_to_gdrive.sh` put the secret list before the junk list (P2-2, script side); then update `backup_filter.expected_filter_args` to match, or the folder backup refuses to run.
- [ ] `P3` `security` `@ai` B1 review lows: the drift check reads only the first `RSYNC_OPTS` block (P3-2); `backup_folders.txt` entries that are absolute or contain `..` escape `~/Documents` and the Drive folder (P3-4).
- [ ] `P1` `bug` `@ai` **Quick folder backup notifies the previous full run's result.** It writes no log and `_finished()` (`main.py:2824-2845`) reads `last_backup_info()`, so a failed quick rsync can say "Backup completed successfully"; judge it by its own exit code. (Audit H1)
- [ ] `P1` `bug` `@ai` **Cloud quota fetched over HTTPS on the UI thread** (lab hard rule). `StorageTile.__init__` → `set_usage()` → `cloud_quota.quota()` / `dropbox_account_email()` (`main.py:1580`, `1634-1639`), on every Storage refresh; move into a `CallWorker`. (Audit H2)
- [ ] `P1` `feature` `@ai` **"OK" / "Your Mac is protected" mean copied to the local Drive folder, not uploaded.** Nothing checks Google received the files (`backup_to_gdrive.sh:99` checks only the folder exists). Reword the pill and banner, and add an upload signal (a canary file's Drive `modifiedTime`, or the quota trend). (Audit H3)
- [ ] `P2` `bug` `@ai` **Schedule toggle arms launchd and the in-app timer together, with no lock.** `toggle_schedule` loads the plist and `_maybe_auto_backup` needs it loaded (`main.py:2479`, `2652-2662`); launchd fires at a fixed 03:30 via `open -n … --run-backup` (bypasses the instance lock, ignores mirror mode). Add a lock in `backup_to_gdrive.sh` and decouple the two. (Audit M1)
- [ ] `P2` `bug` `@ai` **A run that aborts before its finish line fires no notification or webhook** (Drive not mounted, rsync missing): `run_status()` gives `—` and `_finished()` sends nothing; treat a non-zero exit as an error. (Audit M2)
- [ ] `P2` `bug` `@ai` **Quit is `os._exit(0)` with no `shutdown()` naming the threads** (lab rule; `main.py:5283`); a mid-write `env_last_use.json` or state file can be truncated. Add `shutdown()` over the keeper's threads and atomic JSON writes. (Audit M3)
- [ ] `P2` `bug` `@ai` **Lab Health trashes envs on the last scan's eligibility.** `cleanup_targets()` trusts `item["eligible"]`; re-check `env_users()` just before `moveToTrash` as the Worktrees dialog does. Also move the cleanup's `rmtree`/`pip freeze` off the UI thread. (Audit M4, L1)
- [ ] `P3` `security` `@ai` Audit lows: `state.json` (webhook URL) is mode 644; tokens are written before `chmod`; `secret_name_patterns.txt` covers only `.env` names (no `*.pem`, `credentials*.json`, `token*.json`); no "Secrets not backed up" status as the spec promised; the Proton check looks at any account, not the vault's `latest.tar.gz`. (Audit L3–L5)
- [ ] `P3` `docs` `@ai` Dry run is not quite "no files changed" (`mkdir -p` of Drive folders, `backup_to_gdrive.sh:105,132`); app-context says tokens are in the Keychain, they are `tokens.json` (mode 600). Fix wording when filling in app-context. (Audit L2)
- [ ] `P2` `testing` `@me` Owner checks from the audit: confirm a file changed today has today's time on drive.google.com; `launchctl start com.andreas.gdrive-backup` with the app quit (explains exit 78); a `restore-secrets.sh` dry-run drill; check why the secrets bundle grew 59 MB → 288 MB on 2026-11-18. (Audit "Checks only the owner can run")

- [x] `P3` `security` `@ai` **Lab Health git hardening and app-context filled** (`docs/specs/workspace-cleanup.md` §19): `lab_health._git` ignores repo-local fsmonitor and hooks; app-context placeholders filled. 2026-11-18.
- [x] `P1` `feature` `@ai` **Workspace cleanup, slice 1** (`docs/specs/workspace-cleanup.md`): Lab Health no longer lists or cleans another agent's worktree (`.claude/`, linked worktrees; it had offered `provisio/.claude/worktrees/*/node_modules`, 966 MB), and a new **🌿 Worktrees…** dialog offers worktrees under the lab only when clean, merged or pushed, 14+ days untouched, nothing running in them and no non-cache ignored files; removal is `git worktree remove` with a restore record, branch kept. Reviewed; tests in `tests/test_workspace.py`, `tests/test_lab_health.py`, `tests/test_worktrees_dialog.py`. Installed as v2.107.
- [x] `P1` `feature` `@ai` **Workspace cleanup, slice 2** (spec sections 14-15): **🗂 Workspace…** dialog (old backups to the Trash after a record, root caches, archive list), worktree/backup age settings, weekly report-only scan. Tests: `tests/test_workspace_extra.py`, `tests/test_workspace_dialog.py`. Built; review and Secure passes in the spec; not installed.
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
- [x] `P1` `feature` `@ai` **Lab Health judges each env by its own last use, and never offers one something runs from.** A `.venv` / `node_modules` is offered after 7 unused days (build/dist keep the 30-day project rule). Last use comes from what running a project leaves behind (installs, `.pyc`, `.pytest_cache`, logs, `uv.lock`, dev caches, Lab Hub launch logs, shell history, project edits) and is remembered across scans in `env_last_use.json`, so a cache cleanup cannot make an env look idle. Never offered: this app's own env, Lab Hub apps run from source, bundles that launch from a checkout, running processes, launchd jobs. Duplicate envs (same manifest or package set) are flagged with the oldest copy marked. Safer rules after the 2026-11-08 22:40 incident; tests in `tests/test_lab_health.py`.
- [x] `P1` `feature` `@ai` **Rebuild record before every env goes to the Trash, plus ♻ Rebuild missing envs.** Rebuild command, Python version and exact freeze saved to `env_records/` first (no record, no trash); the new action recreates missing envs in a worker with per-env results. *Select all safe* now ticks caches only, and the confirm dialog lists each env's last use and rebuild cost.
- [x] `P2` `feature` `@ai` **Lab Health commit warnings and multi-project commit.** ⚠ in the Git column for merges/rebases in progress, detached HEAD, 200+ files, 10+ deletions, secret-like files, un-ignored generated folders, nested repos and files over 5 MB; *Select all with uncommitted changes (N)*, *Commit N projects…* with *Commit only without warnings*. Linked projects can be committed too, always with a linked-project warning.
- [x] `P2` `feature` `@ai` **Lab Health thresholds in the card** (the threshold half of the P3 item below; its `pip freeze` offer is still open): two day boxes, saved to `lab_health_settings.json`. Also right-click *Show largest folders…* and a **🗂 Other caches…** dialog (pip, uv, Homebrew, npm, Xcode, model caches; Docker report-only) that runs each tool's own cleanup. Built as v2.081 (`_build_info.json`, commit 2c4d3cb).
- [ ] `P3` `feature` `@ai` Lab Health: let the 30-day idle threshold be set in the UI, and offer `pip freeze > requirements.txt` for envs locked only for lack of a manifest (shopfront, syndustryx)
- [ ] `P3` `bug` `@ai` `replace_worker()` only disconnects a still-running scan; a `done` already queued can still land before the new result (deferred P3 in `docs/audit/qthread-lifetime-review.md`)
- [ ] `P2` `docs` `@ai` Fill in `docs/foundry/app-context.md`: only Invariants is written; Product, Stack, Commands, hot spots, security surface and test bar are still placeholders
- [ ] `P3` `docs` `@ai` Add a CHANGELOG: the AGENTS.md definition of done requires one and the repo has none
- [ ] `P3` `bug` `@ai` Lab Health: the Envs header tooltip is built before the saved thresholds are loaded, and neither it nor the hint under the day boxes is refreshed after a change, so both can quote the wrong day counts (`LabHealthCard.__init__` in `main.py`; the summary line and Idle tooltip are fine)
- [ ] `P3` `bug` `@ai` Lab Health: the **🗂 Other caches…** button tooltip says "Nothing is deleted from here", but its dialog's **🧹 Clean checked** does delete the ticked caches; reword the tooltip

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
