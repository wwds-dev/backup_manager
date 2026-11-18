# App context

The only app-specific file the Foundry agents read. Fill it in once; keep it short and
true. Agents treat the **Invariants** as hard rules.

## Product
Backup Control Center: a PySide6 macOS menu-bar and window app for one person (the owner). It
monitors cloud storage (Mac disk, Google Drive, Dropbox, iCloud), runs and verifies the nightly rsync
backup to Google Drive, shows Time Machine and git_autosync state, and cleans up the lab workspace
(Lab Health caches and envs, worktrees, backups, system caches). It must never claim a backup is safe
beyond what it checked ("OK" means copied to the local Drive folder, not that Google received it; see
the readiness audit H3), never delete without a ticked box and a confirm dialog, and never touch
another agent's worktree or an out-of-tree project.

## Distribution
tier: public

Status: tier confirmed by the owner on 2026-11-11 ("confirm all nine tiers"). An agent proposed it
the same day from the evidence below; raising it later goes through Comply first.

Evidence: the repo `wwds-dev/backup_manager` is public (checked 2026-11-11); it has no
`LICENSE`, no GitHub release, no download page and no store listing. Nobody pays and it takes no
payment. Personal data: the owner's own backup folder list and Google Drive / Dropbox OAuth
tokens (a mode-0600 file in Application Support, not the Keychain; corrected 2026-11-18), nobody else's. `public` is proposed only because the source is published; if
nobody else is meant to use it, making the repo private and setting `internal` removes the
LICENSE, privacy note, name check and sign-off.

## Stack
Python 3 in a uv-managed `.venv` (no version pin), PySide6 (Qt; unpinned) and `requests`
(`requirements.txt`). Shell: `rsync` and bash scripts under `_Admin/backup/`, `launchctl`, `tmutil`,
`pmset`, `lsof`, `git`, `gitleaks`. Packaged with PyInstaller. Single large `main.py` plus
`lab_health.py`, `workspace.py`, `workspace_extra.py`, `cloud_quota.py`, `verify.py`, `appkit_guard.py`,
`version.py`. macOS only.

## Commands
- Install deps: `uv pip install -r requirements.txt` into `.venv`
- Run tests: `.venv/bin/python -m pytest` (one mode; `pytest.ini`: `testpaths = tests`, `--strict-markers`)
- Lint / types: none configured
- Build / package: `./build_app.sh` (PyInstaller, stamps the version, installs to /Applications)
- Release smoke test checklist: launch the installed app; the window title shows the new `v<MAJOR>.<BUILD>`;
  Overview loads; Lab Health scan runs; quit; relaunch with `state.json` settings intact.

## Docs and process files
`README.md` (product, config files, tests, versioning), `TODO.md` (backlog, priority/owner legend),
`SUGGESTIONS.md`, `SECURITY.md`, `SUPPORT.md`, `LICENSE`. No CHANGELOG file: changes are recorded as
done items in `TODO.md` and the spec's verify and release logs in `docs/specs/`. Version is
`v<MAJOR>.<BUILD>` from `VERSION` and `git rev-list --count HEAD` (README "Version"). UI entry points:
the sidebar pages and the menu-bar icon in `main.py`.

## Architecture hot spots
- Threads: every `QThread` starts via `start_thread()` (see Invariants); the Overview and scans use workers.
- Single instance: `gui.lock` (`fcntl`) in `~/Library/Application Support/Backup Control Center/`; launchd's
  `--run-backup` bypasses it.
- State: `state.json` (settings, overdue cooldown, webhook URL), `tokens.json`, `env_last_use.json`,
  restore records, all in that folder (`cloud_quota.SECRETS_DIR`).
- Module boundaries: Qt-free rules in `lab_health.py`, `workspace.py`, `workspace_extra.py`; widgets in `main.py`.
- Nested repos: Lab Health walks `lab/active/<project>/`, other agents' repos and worktrees.
- External: Google Drive and Dropbox APIs (`cloud_quota.py`), `_Admin/backup/*.sh`, launchd, Time Machine.

## Security surface
- Secrets: Google Drive and Dropbox OAuth tokens in `tokens.json` (mode 600, not the Keychain); a webhook
  URL in `state.json`. The secrets vault and plaintext findings are in `docs/specs/secrets-vault.md` and the
  readiness audit.
- Network: HTTPS to Google and Dropbox quota APIs; the failure webhook.
- Untrusted input: repo-local git config and hooks, and branch, folder and file names in other agents'
  repos (git runs with `core.fsmonitor=false`, `core.hooksPath=/dev/null`); plist and bundle contents.
- File writes and deletes: rsync to Drive, Trash moves with restore records, permanent cache deletes.
- Dependencies: `requirements.txt` (unpinned). Packaging: PyInstaller `.app` from `build_app.sh`.

## Test bar
No coverage target (`pytest-cov` is not installed). Tests live in `tests/`, one file per module or page,
with `tmp_path` and patched app-data folders so a run never touches live data. New logic is
mutation-checked by hand. A test that passes alone and fails in the suite, or the reverse, is flaky and
is fixed, not rerun. `test_appkit_guard.py` needs the `lab_hub` checkout beside this repo.

## Invariants
<things agents must never do or imply, e.g. "no real money", "no network calls", copy rules>
- Start every background `QThread` with `start_thread()` (or `replace_worker()`) in `main.py`, never bare `.start()`: the keeper holds it until `finished`, so no owner (a tile deleted by refresh, a closed dialog) can destroy it mid-run. Never `QThread.terminate()`. Guarded by `tests/test_thread_lifetime.py`.

## Models used
None. Inventory from the code on 2026-11-11 (Foundry v9): no model is called. The only match is the Lab Health page measuring the size of `~/.cache/huggingface` on disk (`lab_health.py:1181`), not a model call.

## Domain specialist
None. For a regulated or expert domain (money, insurance, health, law, ...), name the key
(`finance`, `insurance-compliance`, ...) and list: the domain, the rules and standards that apply
(with jurisdiction), what the reviewer must check, and the claims this app must never make.
`/new-app` and `/adopt-app` propose it; `install.sh --with domain-<key>` installs the reviewer.

## Optional roles installed
None.
