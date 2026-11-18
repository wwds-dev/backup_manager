# Code-level readiness audit: promises vs code (2026-11-18)

Foundry phase: **Verify** (read-only QA audit; nothing fixed). Audited on branch
`claude/workspace-cleanup-slice1` at `2946be7` (another session's committed feature branch, not
`main`), plus the lab's `_Admin/backup/` scripts as they are on disk. Nothing was run that backs up,
cleans, purges, deletes, moves or uploads; the vault scripts were read, not run. No secret value was
read: only file and key names.

Test suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` → **196 passed, 0 failed**,
10 deprecation warnings (`QNetworkInformation.load`, `main.py:2457`). One run.

## Verdict

**The nightly Google Drive copy can be trusted as a local copy, not yet as a verified cloud backup.**
Recent logs show a full run that finished OK on 13, 14, 15, 16, 17 and 18 November, each with
`SECRETS: OK` to the Proton vault. But "OK" and the green **Your Mac is protected** banner mean only
that rsync wrote into the Google Drive app's local folder; nothing checks that Google received it,
and the spot-check (`verify.py`) is unreachable and would only check the same local folder. Two code
paths break promises outright: the right-click **Back up now** for one folder copies `.env` files to
Google Drive in plaintext and then reports success from an older run, and the Storage page fetches
cloud quota over HTTPS on the UI thread (lab hard rule). Lab Health's deletion paths are sound:
caches and envs are filtered as promised, envs go to the Trash only after a rebuild record, and
worktree removal re-checks every gate and never forces.

## Leads from the doc sweep

| Lead | Result | Evidence |
|---|---|---|
| `verify.py` has no caller | **Confirmed** | Nothing in `main.py` imports it (`grep verify main.py` is empty); README.md:145 says so. Already TODO (v3, "Wire `verify.py` into the app"). |
| `replace_worker()` only disconnects a still-running scan | **Confirmed, low impact** | `main.py:1267-1279`: `done` is disconnected only when `old.isRunning()`. A finished thread whose queued `done` is undelivered still lands, but before the new result, which then overwrites it. Already TODO (P3). |
| FDA re-grant after every rebuild; launchd fallback unreliable | **Confirmed** | README "Full Disk Access" (re-grant); `launchctl list` shows `com.andreas.gdrive-backup` last exit **78**; `logs/launchd.err.log` (last written 2026-06-27) holds "Operation not permitted" from the older bash form. Why the current `open -n … --run-backup` form exits 78 is unconfirmed. |
| Google Drive is the only destination; no restore helper | **Confirmed for Drive; refuted for secrets** | `backup_to_gdrive.sh` writes only under `$DRIVE_ROOT`. No Drive restore exists (TODO P3). Secrets do have one: `active/git_autosync/restore-secrets.sh`. |
| Vault cannot run until the owner signs a Proton account in | **Refuted** | Every full run 2026-11-13 → 2026-11-18 logs `SECRETS: OK - secrets_<date>.tar.gz … in the opaque1337@proton.me vault` and rotates old bundles. The P0 TODO "Sign `opaque1337@proton.me` in" looks done (owner to tick). Per the spec's order, the purge (P1 `@me`) is now unblocked. |
| `docs/foundry/app-context.md` mostly empty | **Confirmed** | Only Distribution, Invariants, Models used and Domain specialist are written (`app-context.md:261-299` are placeholders). It also says OAuth tokens are in the Keychain (`:271-272`); they are a mode-600 JSON file (`cloud_quota.py:69-72`, `tokens.json`). Already TODO (P2). |

## Findings

### Blocker

**B1. Folder "Back up now" copies `.env` files to Google Drive in plaintext.**
Promise: secrets never go to Google Drive (spec `secrets-vault.md` "Required behaviour" 2;
`secret_name_patterns.txt` header). Code: `run_single_folder()` (`main.py:2565-2594`) runs rsync with
`--exclude-from=gdrive_backup_excludes.txt` only; the secret-name list is applied only by the script
(`backup_to_gdrive.sh:51`), and `gdrive_backup_excludes.txt` has no `.env` pattern. Right-click `lab`
→ Back up now copies `sentinel/.env` and every other `.env*` under it to `Backups/MacBook/Documents/`,
and Google keeps it in Trash and version history after removal. That would leak the keys the owner is
about to rotate. Smallest fix: pass `--include='*.example' --include='*.sample' --include='*.template'`
and `--exclude-from=secret_name_patterns.txt` in `run_single_folder` (or run the script with a
one-folder env var), plus a test that the argument list contains the secret patterns. The Excludes
**Preview matches** (`main.py:2203`) has the same gap: it never shows `.env` as skipped.

### High

**H1. Quick folder backup reports the previous run's result as its own.**
Promise: "A macOS notification fires when a real backup finishes (success or errors)" (README,
Notifications). Code: the quick run writes no log; `_finished()` (`main.py:2824-2845`) reads
`last_backup_info()`, i.e. the newest *full* run in the logs, so a failed quick rsync (exit code
never read) still notifies "Backup completed successfully" when last night's run was OK. Fix: track
the quick run separately and judge it by `QProcess.exitCode()`; or route it through the script so it
logs.

**H2. Cloud quota is fetched over the network on the UI thread** (lab hard rule: nothing on the UI
thread may fetch). `StorageTile.__init__` calls `set_usage()` (`main.py:1580`), which calls
`cloud_quota.dropbox_account_email()` and `cloud_quota.quota()` (`main.py:1634-1639`): a token refresh
plus an API call per connected account, 20 s timeouts each (`cloud_quota.py:235,250,319,334`). It runs
from `StorageCard.refresh()` on the 5-minute timer, on network-up, on Refresh all and on a theme change
(`main.py:5149`). With a slow network the window freezes for up to 40 s per account. Fix: move the
quota and email fetch into a `CallWorker` via `start_thread()`, update the tile in the slot.

**H3. "OK", "Up to date" and "Your Mac is protected" mean written to the local Drive folder, not
uploaded.** Promise: README Overview ("green **Your Mac is protected** when every backup job is
fine"), job pill "Up to date". Code: the only Drive check is that the mount folder exists
(`backup_to_gdrive.sh:99`, `main.py:2667`); success is rsync's exit code into
`~/Library/CloudStorage/GoogleDrive-…/My Drive`. If the Google Drive app is paused, signed out, out of
quota or stuck, runs keep reporting OK while nothing reaches Google. `drive_job()` /
`protection_banner()` (`main.py:4434-4541`) have no upload signal. Fix (narrowest): reword the pill
and banner to "copied to Google Drive folder", and make the Storage quota sparkline (or a Drive API
`modifiedTime` check on one canary file per run) the upload signal. Unverifiable without a live run:
see owner checks.

### Medium

**M1. In-app schedule and launchd fallback are the same switch, with no lock.** The **🕒 Nightly
schedule** toggle loads/unloads the launchd plist (`toggle_schedule`, `main.py:2652-2662`), and the
in-app timer only runs when that job is loaded (`_maybe_auto_backup`, `main.py:2479`). So enabling the
schedule always arms both. The plist fires at a hardcoded 03:30 (plist `StartCalendarInterval`) and
`open -n` starts a second process in `--run-backup` mode (`main.py:36-39`), which bypasses the
single-instance lock; `backup_to_gdrive.sh` takes no lock. If the timer tick lands first, two runs
can overlap on the same log and destination. Also: the Settings backup time never reaches the plist,
and `--run-backup` never sets `MIRROR=1`, so launchd runs ignore mirror mode. Fix: a `flock` (or
`mkdir` lock) at the top of the script; decouple the schedule state from `launchctl list`.

**M2. A run that aborts early fires no notification and no webhook.** Promise: webhook "when a backup
finishes with errors" (README Settings). Code: a run that stops before its finish line (Drive not
mounted, rsync missing, no folders: `backup_to_gdrive.sh:93-110` exit 1 after "started") is status
`—` (`run_status`, `main.py:960-966`), so `_finished()` sends neither the error notification nor the
webhook. The Overview does show "Last run unfinished". Fix: in `_finished()`, treat a non-zero exit
code or a missing finish line as an error.

**M3. Quit skips every thread; there is no `shutdown()`.** Lab rule: `shutdown()` must name every
QThread. Code: the tray Quit calls `os._exit(0)` (`main.py:5283`) by design. A Lab Health scan saving
`env_last_use.json`, a rebuild, a worktree removal or a JSON state write can be cut mid-write; a
truncated `env_last_use.json` makes envs look idle sooner on the next scan. Fix: a `shutdown()` that
lists the keeper's threads, requests interruption and waits briefly, and writes state files
atomically (temp file + `os.replace`).

**M4. Env eligibility is not re-checked at cleanup time.** Promise: an env "is never offered when …
a running process has a path inside it" (README Lab Health, In use). Code: `cleanup_targets()`
(`lab_health.py:1074-1100`) trusts `item["eligible"]` from the last scan; `clean_checked()`
(`main.py:3708-3777`) trashes without a fresh process or launchd check. An env started between scan
and click goes to the Trash. Worktree removal does re-check (`workspace.py:316-329`). Fix: re-run
`env_users()` for each env target just before `moveToTrash`.

### Low

- **L1. Cleanup runs on the UI thread.** `clean_checked()` runs `shutil.rmtree` and, per Python env,
  `uv pip freeze` / `pip freeze` with 90 s timeouts (`lab_health.py:846-863`) on the GUI thread; so
  do commits with gitleaks (`main.py:3612`). No network, so not a hard-rule breach, but the window
  can hang for minutes. Move into a `CallWorker`.
- **L2. Dry run is not quite "no files changed".** With `DRY_RUN=1` the script still `mkdir -p`s the
  destination and each folder on Drive (`backup_to_gdrive.sh:105,132`) and runs the lab-root snapshot
  in report-only mode. Empty folders only.
- **L3. The vault failure has no tile of its own.** Spec Architect: "BCC's tile shows 'Secrets not
  backed up'"; there is no such UI. A vault failure shows only as the whole run "WITH ERRORS". The
  **Proton vault mount check** (`main.py:4095-4119`) checks any `ProtonDrive-*` folder, not the vault
  account or `latest.tar.gz`.
- **L4. Secret names are `.env`-family only** (`secret_name_patterns.txt`). `*.pem`, `id_rsa`,
  `credentials*.json`, `token*.json`, `client_secret*.json` would go to Google in plaintext. None
  exist today under the backed-up folders (only public `certifi/cacert.pem`), so latent.
- **L5. `state.json` is mode 644** (`_save_state`, `main.py:1154`) and holds the failure webhook URL,
  which for ntfy/Slack is a bearer secret. `tokens.json` and `app_credentials.json` are 600, but
  written before `chmod` (`cloud_quota.py:71-72`), a brief window in a 755 folder.
- **L6. Caches are deleted permanently by name**, including a generic `.cache` folder, which some
  tools use for downloaded models or data. Regenerable by download, but not "recreated
  automatically" for free.
- **L7. Secrets bundle grew from 59 MB (11-17) to 288 MB (11-18).** Not a bug found in code; worth a
  look at what entered `secret_paths.txt` folders.
- Existing TODO items confirmed and not duplicated: Other caches tooltip says "Nothing is deleted"
  (`main.py:3068-3070`), Envs header tooltip stale thresholds, no CHANGELOG.

## Promise inventory

| Promise (where) | Status |
|---|---|
| Nightly Drive backup via in-app timer, network and USB triggers (README) | Delivered (logs show daily runs); see M1 for overlap |
| launchd fallback (README, SETUP.md) | Narrower: unreliable, exit 78 (lead 3) |
| Run / Dry run / Pause / Stop / Preview deletions (README) | Delivered; dry run creates empty folders (L2) |
| Folder right-click Back up now (README) | Narrower and unsafe (B1, H1) |
| Mirror mode archives deletions under `_deleted/` (README) | Delivered in the script; not applied to launchd runs (M1) |
| Status, History, per-folder last synced from logs (README) | Delivered (per-run parsing, `main.py:945-1032`) |
| Overdue notice once per hour, tray dot (README) | Delivered (tested) |
| Failure webhook (README) | Narrower (M2) |
| "Your Mac is protected" / Up to date (README Overview) | Narrower (H3) |
| Backup verification (README "Verifying a backup") | Stub in the app: library only (lead 1) |
| Secrets to Proton vault, not Google (spec, BACKUP_STRATEGY via SETUP) | Delivered by the nightly script (logs); broken by B1; L3, L4 |
| Secrets restore (spec item 4) | Delivered in git_autosync (`restore-secrets.sh`); restore drill unverified |
| Plaintext purge (spec item 3) | Unverifiable here: owner runs it |
| Storage tiles, quota, sparkline (README) | Delivered, but fetch on UI thread (H2) |
| Lab Health: caches permanent, envs to Trash with rebuild record, gates (README) | Delivered (`lab_health.py:1074-1100`, `main.py:3750-3768`); M4, L1, L6 |
| Lab Health never lists another agent's worktree (spec workspace-cleanup) | Delivered (`main.py:1442`, `lab_health.py:1056-1071`) |
| Worktrees dialog: every gate, re-check, never forced, branch kept (README) | Delivered (`workspace.py:193-334`) |
| Time Machine status and Back up now (README) | Delivered (tested parsing) |
| Single instance, Open at login, menu bar, appkit_guard (README) | Delivered (`main.py:5500-5545`, tests) |
| QThread keeper, no `terminate()` (app-context Invariants) | Delivered; no `shutdown()` (M3) |
| Frozen app writes only under Application Support (lab rule) | Delivered for app state; writes the lab's `backup_folders.txt` / excludes by design |

## Checks only the owner can run

1. **Upload is real:** in drive.google.com, open `Backups/MacBook/Documents/lab/` and confirm a file
   changed today has today's modified time; check Google One quota has room.
2. **Drive app signed out/paused:** pause Google Drive, press Run backup now, see whether the app
   still says OK (it will, per H3).
3. **launchd fallback:** quit the app from the menu bar, then `launchctl start com.andreas.gdrive-backup`
   and check for a new `backup_<date>.log` run (explains exit 78).
4. **Secrets restore drill:** `restore-secrets.sh latest.tar.gz --into <scratch> --dry-run` from
   git_autosync, per the spec's success measure.
5. **Purge:** now that the vault writes nightly, run `purge_plaintext_secrets.sh` (list), then
   `--apply`, then empty Drive's Trash — but only after B1 is fixed, or a quick backup re-adds them.
6. **Rotate keys** (existing P0), after B1 and the purge.
7. **FDA after the next rebuild:** re-grant and confirm the first run reads every folder.
