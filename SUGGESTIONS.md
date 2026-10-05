# Backup Control Center — Suggestions

Status: `IDEA` · `CONSIDERING` · `PLANNED` · `DONE` · `REJECTED`

---

## Open

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 1 | Developer ID code signing — removes the Full Disk Access re-grant after every rebuild and makes the launchd fallback reliable. Needs a paid Apple Developer account; cannot be done in code alone. | infra | M | BLOCKED |
| 4 | Restore helper — pick a dated log, restore what that run moved | feature | XL | DEFERRED |
| 5 | S3 / Backblaze B2 as a second destination | feature | XL | DEFERRED |
| 7 | Power Nap backup via an `SMAppService` helper daemon | research | L | IDEA |
| 8 | macOS Shortcuts action that triggers `--run-backup` | feature | M | IDEA |
| 9 | Focus-mode notification filter, so overdue alerts stay quiet during Do Not Disturb | feature | M | IDEA |

## Done

| Suggestion | When |
|---|---|
| Lab Hub integration — launchable from the hub, which also shows its running state | Aug 2026 |
| Storage tiles no longer escape the window as floating panels (parentless-widget shows, and `setParent(None)` on a visible tile) | Oct 2026 |
| Open at login starts in the menu bar only — LaunchAgent with `--background` instead of a login item | Oct 2026 |
| Backup pause / resume (SIGSTOP / SIGCONT) | Aug 2026 |
| Tray icon badge (orange dot) when overdue | Aug 2026 |
| Log scroll position restored on relaunch | Aug 2026 |
| Confirm before Quit from tray | Aug 2026 |
| Per-folder last-synced timestamp in the Folders card | Aug 2026 |
| Exclude patterns "Preview matches" dialog | Aug 2026 |
| Backup triggered on USB volume mount | Aug 2026 |
| Backup schedule time picker in Settings | Aug 2026 |
| Quick-backup a single folder (right-click in Folders card) | Aug 2026 |
| Wake Mac time tracks the backup time setting | Aug 2026 |
| Quota trend sparkline in storage tiles (QPainter, no extra deps) | Aug 2026 |
| Webhook / ntfy / Slack POST on backup failure (configurable in Settings) | Aug 2026 |
| Mirror mode (`MIRROR=1`) plus a "Preview deletions" button — the backup can finally drop data deleted locally, with removals archived to `_deleted/<date>/` instead of destroyed | Sep 2026 |
| Backup verification spot-check — `verify.py` compares source against the backup by size/mtime (not checksums: nothing needs a read since Drive streams the destination on demand), honouring rsync's excludes, `--update`, and `--modify-window=2`. Tested; not yet reachable from the app (no button or flag calls it) | Aug 2026 |
| Storage tiles (Local, Google Drive, Dropbox) with progress bars | v1 |
| Cloud accounts OAuth quota dialog (Google + Dropbox) | v1 |
| Nightly backup timer in-app, replacing launchd | v1 |
| Backup history table with Transferred column and per-row log viewer | Aug 2026 |
| Live log output plus pre-populated last 60 lines at launch | Aug 2026 |
| macOS notification on finish, overdue notification with cooldown | Aug 2026 |
| Network-triggered backup on reconnect | Aug 2026 |
| Menu-bar icon with tray menu and single-instance guard | Aug 2026 |
| Dark mode with live reload and manual toggle | Aug 2026 |
| Lab Health card (sizes, git status, cleanup) | Aug 2026 |
| Backup destination health check before a run | Aug 2026 |
| iCloud local cache tile and Time Machine status card | Aug 2026 |
| `rsync --stats` and `--itemize-changes` on every run | Aug 2026 |
| Per-run (not per-day) backup history — multiple runs sharing one daily log were collapsing to the day's first run's status everywhere it was read | Sep 2026 |

## Rejected

| Suggestion | Why |
|---|---|
| Keyboard shortcut Cmd+R to run backup | Not needed — the button is right there |
