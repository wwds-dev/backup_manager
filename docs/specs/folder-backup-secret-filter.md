# Spec: the one-folder backup keeps secrets off Google Drive

Needs: define, build, review, verify, secure, docs
Status: built and reviewed 2026-11-20 on `claude/folder-backup-secret-filter-334e2b`; not merged, built or
installed. Fixes readiness audit B1 (`docs/audit/2026-11-18-readiness-audit.md`, TODO P0).

## Define
The right-click folder **Back up now** (`BackupStatusCard.run_single_folder`) ran rsync to the Google Drive
folder with `gdrive_backup_excludes.txt` only, so `.env` files went to Drive in plaintext. The nightly
script (`_Admin/backup/backup_to_gdrive.sh`) lets `*.example`, `*.sample`, `*.template` through, then
excludes the junk list and `secret_name_patterns.txt`. The Excludes **Preview matches** showed only the
junk patterns, so it gave a wrong picture.

Success measure: a test with a fake runner and dummy secret-named files shows the one-folder rsync
arguments carry the secret filter in rsync order; a real local rsync between two `tmp_path` folders
copies no secret name and every example/sample/template file; a test fails if the script's filter
changes without the app. Phases skipped: Design (no new screen; two strings), Architect (one Qt-free
module, no state, threads or boundaries), Comply/Launch/Release (not released here; owner asks).

## Build
- `backup_filter.py` (Qt-free): `rsync_filter_args(BACKUP_DIR)` parses the `--include` / `--exclude-from`
  arguments of the script's `RSYNC_OPTS`, resolves `$SCRIPT_DIR` and `$EXCLUDES`, and returns them only
  if they equal the app's expected list and `secret_name_patterns.txt` has patterns; otherwise
  `FilterError`. One source (the script), checked on every run, so drift fails closed instead of leaking.
- `main.single_folder_rsync_args()` builds the full argument list; `run_single_folder` shows a warning
  and starts nothing on `FilterError`.
- Preview matches walks the first three folders once with the same rules in rsync's first-match order
  (`preview_rules`, `excluded_paths`), lists an excluded folder once without walking into it, and tags
  secret names.

## Verify (2026-11-20)
- `tests/test_backup_filter.py`: 13 tests at build, 19 after the review fixes. Full suite `.venv/bin/python -m pytest`: 253 passed,
  1 skipped (`test_appkit_guard` needs the `lab_hub` checkout beside the repo; a worktree has none).
- Mutation check by hand, each reverted: old B1 argument list; drift check off; empty-list check off;
  preview without secrets; preview without the includes; includes after excludes; card ignoring the
  error. All 7 killed.
- Found while testing: macOS APFS is case-insensitive but rsync patterns are not, so `.Env` (or other
  mixed case not listed) would pass both the nightly script and this path. The pattern list lives in
  `_Admin/backup/secret_name_patterns.txt`, outside this repo: follow-up, see Secure.

## Secure (2026-11-20)
Independent read-only review by the `security-engineer` agent (not the author):
`docs/audit/folder-backup-secret-filter-security.md`. Verdict: pass with findings, no P0 or P1.
App-side P2-2, P3-1 and P3-3 fixed after it (see the follow-up there); full suite then 259 passed,
1 skipped. P2-1 (letter case), the script-side half of P2-2 and P3-2/4/5 are open in `TODO.md`.
