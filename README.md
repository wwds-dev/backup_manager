# Backup Control Center

![Screenshot](docs/screenshot.png)
A PySide6 desktop app to monitor cloud storage and manage the custom Google Drive
backup (the rsync job in `_Admin/backup/`).

## What it does

Single-screen, scrollable dashboard with seven cards plus a menu-bar icon. Launches
maximized. The **☀/🌙** and **⚙** buttons live in the top-right of the header.

---

### Storage
Local Disk, Google Drive, Dropbox, and iCloud Drive tiles — each with a fill bar
(amber at 70 %, red at 90 %). Google Drive and Dropbox show real cloud quota once
connected via OAuth; iCloud shows local cache size only (Apple publishes no quota API).
Unmounted drives are hidden. Duplicate CloudStorage mounts for the same account are
deduplicated. Tiles auto-refresh every 5 minutes **and** immediately when the Mac
reconnects to the network.

- **☁ Cloud accounts…** — enter a Google OAuth Client ID/Secret or Dropbox App
  Key/Secret once; Connect each mount to show real used/total quota. Expired tokens
  show a red "Token expired — reconnect →" link.
- **+ Add account** — monitor a quota-enabled account that has no local mount.
- Connected Google Drive and Dropbox tiles show a **quota sparkline** (last 60 samples)
  drawn below the fill bar so you can see whether usage is growing.

---

### Google Drive Backup
Last run timestamp, status (OK / WITH ERRORS), and a live log pre-populated with the
last 60 lines of the most recent run so status is visible without triggering a new backup.

**Controls:**

| Button | Effect |
|---|---|
| **▶ Run backup now** | Starts the rsync backup immediately (aborts with a warning if Google Drive is not mounted) |
| **⏸ Pause / ▶ Resume** | Suspends or resumes the running rsync process (SIGSTOP/SIGCONT) — useful when bandwidth is needed mid-backup |
| **⚟ Dry run** | Previews what rsync would copy — no files changed; writes to `dryrun_*.log` so it never confuses the auto-backup detector |
| **🗑 Preview deletions** | Lists what mirror mode would remove from Drive, and changes nothing. Run this before turning mirroring on |
| **📋 History** | Last 15 runs: date, start time, duration, bytes transferred, colour-coded status, and a **📄 View log** button for the selected row |
| **■ Stop** | Kills the running backup or dry run |

**Toggles:**

| Toggle | Effect |
|---|---|
| **🕒 Nightly schedule** | Enables the in-app auto-backup timer (time is configurable in ⚙ Settings) |
| **⏰ Wake Mac** | `pmset` wake schedule set 5 min before the backup time — **required** for overnight backups when the Mac sleeps |
| **🚀 Open at login (menu bar only)** | Installs a LaunchAgent that opens the app with `--background` at login — menu-bar icon only, no window and no dock tile (see *Starting at login* below) |
| **🌐 Network trigger** | Label showing whether the network-reconnect trigger loaded successfully |

**Notifications:**
- A macOS notification fires when a real backup finishes (success or errors).
- If the last successful backup is more than 25 hours ago, an overdue warning fires —
  at most once per hour (cooldown persists across restarts) so a long sleep doesn't
  flood Notification Centre.
- The tray icon shows an orange dot overlay when a backup is overdue.

---

### Backed-up Folders
Add or remove folders from the rsync job (confirmation required before removal), edit
rsync exclude patterns, and see the total local size of the backup set.

- Each folder shows its **last-synced timestamp** (scanned from the most recent log).
- **Right-click any folder** → "Back up now" runs rsync for just that one folder — no
  need to wait for the full nightly run after a large edit.
- **Exclude patterns → 🔍 Preview matches** — runs `find` against your backed-up folders
  for each pattern and shows what would be skipped, so you can verify excludes before
  the next run.

---

### Lab Health
Table of every project in `lab/active/` with total size, reclaimable space (`.venv`,
`build`, `dist`, `__pycache__`, etc.), git status, and manifest/`.env` warnings.

- **🧹 Clean up checked** — deletes reclaimable folders after a confirmation dialog
- **🔄 Rescan** — refreshes the table (also runs at launch and on Refresh all)
- **Right-click any row** → Open in Finder or Open in Terminal

Rebuild a cleaned venv with `uv sync` or `pip install -r requirements.txt`.

---

### Time Machine
Last backup date, idle/running status (with phase and percent while running), and a
**⏱ Back up now** button. Refreshes every 5 minutes alongside the other cards.

- With no backup disk chosen, the card says Time Machine is not set up and the button
  becomes **Set up Time Machine…**. `tmutil startbackup` exits 0 silently in that
  state, so the destination is checked first; otherwise "backup requested" would be a lie.
- When the disk is not plugged in, the last backup reads *unknown — backup disk not
  connected* rather than *none found*: `tmutil latestbackup` cannot see past an
  unmounted disk and reports that on stderr with exit code 0.
- Status comes from `tmutil status -X` (a plist), never the text form, which prints
  `Running = 0;` when idle.

---

### Tools & Links
Quick launchers and helpers:

- **Open locations** — backup destination, logs directory, CloudStorage, iCloud Drive,
  Time Machine settings.
- **Documentation** — in-app viewer for README, Backup Strategy, Google Drive Setup,
  Proton Vault Guide, and Lab Overview.
- **Account pages** — Google One, Dropbox, Proton, iCloud storage pages.
- **Tools** — Google Photos Takeout guide, Proton vault mount check, Time Machine
  back up now (quick shortcut; the full card above has richer status).

---

### Menu-bar icon
Tooltip shows the last backup timestamp; the icon gains an orange dot when a backup
is overdue. Clicking the icon opens the menu and nothing else — it never raises the
window on its own.

| Item | Effect |
|---|---|
| **Open** | Shows the window and returns the app to the dock |
| **Dry run** | Preview run, window opens so you can watch the log |
| **Sync now** | Real backup, window opens so you can watch the log |
| **Quit** | The one true exit — fully terminates the app |

**Quitting keeps the menu-bar icon.** Dock → Quit, ⌘Q, and closing the window all
hide the window *and drop the app out of the dock*, but leave it running in the menu
bar so the nightly schedule, network trigger and USB trigger keep working. macOS calls
this an accessory app; the app switches its own activation policy at runtime.
A notification says so, since a Quit that visibly does nothing looks like a hang.

### Starting at login

**It is a LaunchAgent, not a login item.** `com.wwds-dev.backup-control-center.login`
runs `open -a "/Applications/Backup Control Center.app" --args --background`, and
`--background` is the whole reason: the app comes up as a menu-bar accessory with no
window and no dock tile, which is what a background backup minder should do when you
log in.

A macOS login item **cannot pass arguments**, so the login item this toggle used to
create could only start the app the default way — window in the foreground, dock tile,
every single login. The app had `--background` all along and no way to ask for it.
Same shape as Lab Hub's `com.netrunner3000.labhub.login`, for the same reason.

Two details that are easy to get wrong:

- `--background` sets the accessory activation policy **before the window is built**.
  The bundle has no `LSUIElement`, so the app starts Regular and would otherwise claim
  the dock tile before anything hid it.
- An existing login item is converted on first launch (`migrate_login_item()`) and
  deleted when the agent is installed. Leaving both in place means both fire, and the
  login item is the one that opens a window.

To exit completely, use **Quit** in this menu.

**Reopening a hidden app works normally.** Launching it again — from Lab Hub, Spotlight,
the Finder, or `open -a` — brings the running copy back rather than starting a second
one or doing nothing. A minimized window is restored before it is raised. Closing while
fullscreen first exits the macOS fullscreen Space, then hides after the transition; this
prevents the empty black Space that results from hiding a fullscreen window directly.
See Single-instance guard below.

---

### Dark mode & theme toggle
Matches system light/dark appearance at launch and updates live when the appearance
changes. The **☀/🌙** button in the header overrides the theme for the current session
without touching system settings.

---

### Settings (⚙)
| Setting | Effect |
|---|---|
| **Hide to menu bar on close** | Closing the window hides the app instead of quitting; use Quit from the menu-bar icon to fully exit |
| **Backup time** | Hour and minute for the nightly schedule (default 03:30). The Wake Mac toggle sets a `pmset` wake 5 minutes before this time. |
| **Webhook URL on failure** | A URL to POST to when a backup finishes with errors. Works with ntfy, Slack incoming webhooks, Pushover, or any JSON-accepting endpoint. Body: `{"text": "…", "message": "…"}`. Leave blank to disable. |
| **Mirror mode** | Off by default. On, each run removes backed-up files that no longer exist locally. Enabling it asks for confirmation. See below. |

---

### Mirroring — removing outdated data
By default the backup only ever **grows**: delete a file on the Mac and its copy stays
on Drive forever. That is deliberate (it doubles as accidental-deletion recovery), but
it means the backup drifts from the Mac over time.

Mirror mode fixes the drift without the one thing you should not do — wiping the Drive
copy and re-uploading. A wipe destroys your only offsite copy for the hours it takes
~26,000 files to re-upload, and the drift starts again immediately afterwards.

**Deletions are archived, not destroyed.** Removed files move to
`Backups/MacBook/_deleted/<date>/<folder>/`, which sits beside `Documents` rather than
inside it, so rsync never walks its own archive. Prune those dated folders occasionally,
or they become the thing that grows forever instead.

1. **🗑 Preview deletions** — shows every file mirroring would remove. Changes nothing.
2. If the list looks right, enable **Mirror mode** in ⚙ Settings.

From the command line the same two steps are:

```bash
DRY_RUN=1 MIRROR=1 ~/Documents/lab/_Admin/backup/backup_to_gdrive.sh   # preview
MIRROR=1 ~/Documents/lab/_Admin/backup/backup_to_gdrive.sh             # apply
```

---

## What it deliberately does NOT do
- Does not reconfigure the proprietary sync engines of iCloud, Google Drive, Dropbox,
  or Proton Drive — those stay in their own apps.
- **iCloud Drive and Proton Drive will never show real cloud quota.** No public API
  exists. The iCloud tile shows local cache size only via `du`.
- **Sleep mode suspends everything.** No timer, app, or background process runs while
  the Mac is asleep. Enable **⏰ Wake Mac** so the Mac wakes itself before the scheduled time.

---

## How the nightly backup works

Before Run, Dry run, quick-folder backup, or Preview deletions starts, the app checks the
Google Drive **mount root**, not the final backup destination. The destination may be
missing on a first run or after its contents are cleared; the backup script creates it.
Only an unavailable Drive mount blocks the operation.

Triggered by an in-app timer, not launchd — required because macOS 26 (Tahoe)
removed `spctl --add` and Gatekeeper blocks unsigned apps in non-interactive launchd
contexts.

**Recommended setup:**
1. Set the backup time in **⚙ Settings** (default 03:30).
2. Enable **🕒 Nightly schedule**.
3. Enable **⏰ Wake Mac** so the Mac powers on 5 minutes before the scheduled time.
4. Enable **🚀 Open at login (menu bar only)** so the app is running when the Mac wakes.

**Timer flow:**
1. 5-minute polling timer runs while the app is open.
2. On each tick (and 10 s after launch): if the schedule is enabled, it's past the
   configured time, and no backup has started today at or after that time — the backup fires.
3. rsync runs under the app's Full Disk Access grant.

**Network-triggered backup:** when the Mac comes back online (sleep wake, VPN, outage),
if the last successful backup was more than 12 hours ago and the schedule is enabled,
the app waits 30 seconds for Google Drive to mount then starts a backup automatically.

**USB mount trigger:** when any new volume appears under `/Volumes`, if the last backup
was more than 6 hours ago, a backup starts automatically after a 10-second settle delay.

The launchd job (`com.andreas.gdrive-backup`) remains installed as a best-effort
fallback but the reliable path on macOS 26 is the in-app timer.

---

## Single-instance guard
An `flock` on `gui.lock` keeps exactly one GUI instance alive. A second launch writes
a `show_request` file into the settings directory and exits immediately; the running
copy watches that directory, restores its dock tile and raises its window. So launching
the app while it is already running just brings it back, whether it was merely behind
another window or hidden in the menu bar.

The signal exists because macOS `activate` has no effect on an accessory app, which is
what this becomes after a Quit — the earlier version showed an "already open" alert and
then failed to show anything, which read as the app refusing to launch.

Does not affect `--run-backup` headless mode. Launching with `--background` exits
quietly when another instance is running, and otherwise starts without showing the
window — for starting the app unobtrusively without stealing focus.

---

## Credentials & state
All persistent data lives in:
```
~/Library/Application Support/Backup Control Center/
```
| File | Contents |
|---|---|
| `app_credentials.json` | OAuth Client ID/Secret (Google) and App Key/Secret (Dropbox) |
| `tokens.json` | Per-account OAuth refresh tokens |
| `manual_accounts.json` | Accounts added via + Add account |
| `state.json` | Notification cooldown timestamp, settings preferences |

This location survives `.app` rebuilds. Nothing is stored inside the bundle.

---

## Full Disk Access
Required so rsync can read all Documents subfolders.

> System Settings → Privacy & Security → Full Disk Access → **+** →
> select `/Applications/Backup Control Center.app`

**Re-grant after every rebuild** — the ad-hoc code signature changes each time.

---

## Run from source
```bash
cd ~/Documents/lab/active/backup_manager
uv venv .venv && uv pip install -r requirements.txt
source .venv/bin/activate
python main.py
```

## Build as a standalone app
```bash
cd ~/Documents/lab/active/backup_manager
./build_app.sh
```
Builds `Backup Control Center.app` with PyInstaller and installs it to `/Applications`.
Re-run after any change to `main.py` or `cloud_quota.py`, then re-grant Full Disk Access.

`assets/` holds the app icon source — `icon.iconset/`, the compiled `icon.icns`, and
`make_icon.py` which regenerates both.

---

## Config files

This app owns no configuration of its own for the backup — it reads and writes
the same files the shell script does, so the script keeps working with the app
closed, uninstalled, or replaced. Everything lives in `_Admin/backup/`:

    _Admin/backup/
    ├── backup_to_gdrive.sh              the backup itself; everything else feeds it
    ├── backup_folders.txt               WHICH folders (one per line, relative to ~/Documents)
    ├── gdrive_backup_excludes.txt       WHAT to skip inside them (rsync patterns)
    ├── com.andreas.gdrive-backup.plist  WHEN, as a launchd fallback
    ├── logs/
    │   ├── backup_YYYY-MM-DD.log        one per real run — the app reads these for
    │   │                                  status, history, and per-folder timestamps
    │   └── dryrun_*.log                 previews, named apart so they never count
    │                                      as a backup having happened
    ├── SETUP.md                         first-time install
    ├── BACKUP_STRATEGY.md               why this exists alongside iCloud and Time Machine
    └── PROTON_VAULT.md                  the encrypted vault for sensitive documents

How they relate:

* **`backup_folders.txt` is the source of truth** for what gets backed up. The
  Folders card edits this file and nothing else — do not hardcode the list
  anywhere, or the app and the nightly run will disagree.
* **The logs are the app's database.** There is no separate state store for
  backup history: last-run status, the History table, and the per-folder
  "last synced" column are all parsed back out of these dated files. That is why
  dry runs are written to `dryrun_*.log` — a preview must not look like a run.
* **`DRY_RUN=1` previews without writing.** `DRY_RUN=1 bash backup_to_gdrive.sh`
  adds `--dry-run` and redirects the output to a dry-run log.
* **The plist is a fallback, not the primary schedule.** The app runs the
  nightly backup itself while it is open; launchd covers the case where it is
  not. See *How the nightly backup works*.

The app's own state — window preferences, the notification cooldown, OAuth
tokens, quota history — is separate, and lives outside this folder. See
*Credentials & state*.

| File | Purpose |
|---|---|
| `_Admin/backup/backup_folders.txt` | Folders included in the rsync job |
| `_Admin/backup/gdrive_backup_excludes.txt` | rsync exclude patterns |
| `_Admin/backup/backup_to_gdrive.sh` | The backup script (`DRY_RUN=1` for preview) |
| `_Admin/backup/com.andreas.gdrive-backup.plist` | launchd fallback job |
| `_Admin/backup/logs/backup_YYYY-MM-DD.log` | Dated run logs (include rsync --stats and --itemize-changes output) |
| `_Admin/backup/logs/dryrun_*.log` | Dry-run output (not picked up by backup detection) |

---

## Verifying a backup

`verify.py` spot-checks that the backup really holds what the source does, without
involving the Drive API: the destination is a local Google Drive folder, so a plain
`stat()` comparison is enough. It reproduces rsync's own rules rather than inventing
failures against them — the same `gdrive_backup_excludes.txt` patterns are honoured
(an excluded file is not missing), a destination newer than the source is left alone
deliberately (`--update`), and timestamps only compare to the nearest two seconds
(`--modify-window=2`, `MTIME_TOLERANCE_S`). It samples up to 300 files per folder
by default and checks size and mtime only — never a read, since hashing would drag
a Drive-streamed file back down over the network. A finding is one of **missing**,
**wrong size**, **stale** (changed since the last backup — not a fault), or
**unreadable** (a permissions problem, not a backup problem).

**Not wired into the app yet.** `verify()` is a tested, working library function —
covered by `tests/test_verify.py` — but nothing in `main.py` calls it and there is
no button or CLI flag that runs it today. Run it from a Python shell (`import verify`)
or see the backlog below.

## Tests

```bash
pytest
```

`tests/test_verify.py` covers the comparison rules above against a scratch
source/dest tree (`tmp_path`), and `tests/test_overdue_cooldown.py` covers the
overdue-notification cooldown persisted to `state.json` — both patch the real
state file and secrets directory out so a test run never touches live app data.

## Backlog
- **Developer ID code signing** — eliminates the need to re-grant FDA after each rebuild
  and would let launchd launch the app as a reliable fallback. Requires a paid Apple
  Developer account ($99/yr).
- **Wire up `verify.py`** — the spot-check logic and its tests are done, but nothing
  calls it. A **🔍 Verify backup** button (Google Drive Backup card, or Tools & Links)
  or a `--verify` CLI flag would make it reachable.

## Suggestions & roadmap
See [SUGGESTIONS.md](SUGGESTIONS.md).

## Version

`v<MAJOR>.<BUILD>` — e.g. `v2.050`. **MAJOR** is the product arc, the only
hand-edited part, in the `VERSION` file at the project root. **BUILD** is
`git rev-list --count HEAD`, zero-padded to three digits, so it is derived and
cannot be forgotten: a hand-maintained build number is wrong the first time
someone ships without remembering it, and then silently wrong forever.

The number is shown in the window title. A frozen `.app` has no `.git`, so
`scripts/stamp_version.py` writes `_build_info.json` at package time and
`version.py` reads it back; a checkout prefers live git, so an edit shows up on
the next launch without re-stamping. With neither, it says `v2.???` rather than
inventing a number — claiming a version with no evidence is a lie told in
exactly the moment someone is asking.

This is the lab-wide scheme, shared with `imprint`, `sonar` and `lab_hub`, and
the Lab Project Monitor computes the same string from the same two inputs, so
the dashboard and the running app cannot disagree.
