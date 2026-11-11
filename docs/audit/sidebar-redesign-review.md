# Review: sidebar-redesign (commit a4f18df)

Reviewer: `code-reviewer` agent (Sonnet), read-only, 2026-11-11. Author: a different agent.
`tests/test_overview.py`: 20 passed. No P0. No lost features, broken connections or
thread-invariant violations found; theme toggle still re-styles gauges via `StorageCard.updated`.

## P1
- **Blocking work on the GUI thread, run often.** `OverviewPage.refresh()` calls
  `launchd_loaded()` (`launchctl list`, 15 s timeout) plus `last_backup_info()` /
  `last_backup_age_hours()` (log parsing) on every Overview click, every Time Machine update,
  every Lab Health scan, settings save and backup finish; `refresh_autosync` adds another
  `launchctl list` every 60 s even when the page is hidden. A slow launchctl freezes the window.
  Fix: worker via `start_thread()`, cache 30–60 s, skip the tick when Overview is not visible.

## P2
- **Banner stuck on "Checking your backups…"** when git_autosync has no state files:
  `_LEVEL_RANK["idle"] = 1` outranks `ok`, so `worst_level` returns `idle`. Fix: leave an
  unknown job out of the banner (or rank idle 0); add a test.
- **Incomplete latest Drive run reads green:** `drive_job` checks only `ERRORS`; a newest run
  with status `—` plus an older OK within 25 h shows "Up to date". Fix: warn "Last run incomplete".
- **Running state follows `card.proc` only:** delete-preview and single-folder runs show
  "Backing up…"; scheduler/tray/auto runs are not reflected until the next tick. Fix: start /
  finish signal from `BackupStatusCard`, distinguish the preview.

## P3
- `describe_age`: 36–47 h prints "1 days ago".
- `tm_job`: a non-date `latestbackup` name shows "No backup" though one exists.
- `refresh_gauges`: only the first tile per provider (second Google account not on gauges);
  iCloud gauge shows "—" after each storage refresh until `du` finishes.
- `_show_attention` rebuilds rows on every refresh (button deleted under a click);
  "Open git_autosync" blocks on `run_cmd`.
- Each `SmartScrollArea` installs an app-wide event filter (now 7, never removed).
- `#Muted` / `#SidebarVersion` #8E8E93 on light backgrounds is ~3:1 contrast.

## Test gaps
`OverviewPage.refresh`, `_show_attention`, `refresh_gauges`; `MainWindow` construction,
`show_page`, `_apply_theme`; the new signals; `BackupHistoryView`; the `fit_height_to_rows`
change; idle banner input; incomplete-run case. Suggested: one offscreen `MainWindow` test
with `launchd_loaded` / `run_cmd` patched.

## Resolution (2026-11-11)
- P1 fixed: `OverviewProbe` worker (one `launchctl list` + log reads) via `replace_worker`;
  results reused for 45 s; `refresh()` renders from cache only; the 60 s tick runs only while
  the Overview is visible. Test: `refresh()` with `run_cmd` and log readers patched to fail.
- P2 fixed: `worst_level` ignores `idle` unless nothing else is known; `drive_job` reports
  "Last run unfinished"; running = `proc` and not a dry run/preview, and
  `BackupStatusCard.runs_changed` re-renders on every start. Tests added; each fix
  mutation-checked.
- P3 and the wider test gaps (MainWindow construction, signal wiring) remain open.

## P3 resolution (2026-11-11)
All six P3 items fixed in `main.py`; each has a test in `tests/test_main_window.py`.
- `describe_age`: 36–47 h now reads "1 day ago" (singular).
- `tm_job`: a `latestbackup` name that is not a date shows pill "Date unknown", level warn
  (a backup exists, its age cannot be checked, so neither "No backup" nor green).
- `refresh_gauges`: with several accounts of one provider the gauge shows the fullest one and
  names it ("… · account (fullest of N)"); the iCloud gauge keeps its last finished value while
  a new `du` runs.
- `_show_attention` rebuilds only when its (text, action) list changed; "Open git_autosync"
  uses `QProcess.startDetached`, no `run_cmd`.
- One shared `_WheelRouter` app filter replaces one filter per `SmartScrollArea`; it asks only
  visible areas and drops dead ones. `tests/test_scroll_latching.py` unchanged and green.
- `#Muted` / `#SidebarVersion` use a `muted` token: #636366 light (≥5:1), #98989D dark
  (≥4.5:1 on every dark surface; the old #8E8E93 was 4.3:1 on dark cards).

Test gap closed: an offscreen `MainWindow` test (all backup triggers, `run_cmd`,
`launchd_loaded`, iCloud `du`, the probe and cloud accounts patched) opens every page, toggles
the theme, and drives `storage_card.updated`, `tm_card.updated`, `health_card.scanned` and
`backup_card.runs_changed` into the Overview. Its teardown drains `_thread_keeper`, otherwise
the interpreter aborts at exit. Still open: `BackupHistoryView`, `fit_height_to_rows`, idle
banner input.
