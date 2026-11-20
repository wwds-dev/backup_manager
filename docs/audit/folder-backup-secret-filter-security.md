# Secure review: readiness audit B1 fix (folder "Back up now" and Preview matches secret filter)

- Date: 2026-11-20. Reviewer: security-engineer (read-only; did not write this code).
- Worktree: /Users/as/Documents/lab/active/backup_manager/.claude/worktrees/folder-backup-secret-filter-334e2b
- Reviewed: main.py diff, backup_filter.py, tests/test_backup_filter.py. During the review the change was committed as af932c4; `git show af932c4:backup_filter.py | diff - backup_filter.py` gave no output, so this review covers af932c4.
- Playbook: docs/playbooks/security-engineer.md, last-reviewed 2026-11-11, status current (not stale).
- No secret file was opened. All rsync runs copied dummy files between scratch folders. Nothing was written to ~/Library/CloudStorage. No backup script was run.

## Verdict
PASS WITH FINDINGS. No P0 or P1. B1 is fixed: the one-folder path now uses the same filter as the scheduled script, in the same order, and fails closed when the filter files are missing, empty or out of sync. Two P2 gaps (letter case, and include lines in the editable junk file) affect this path and the scheduled script equally. They are not regressions, but they mean "no secret-named file reaches Drive" holds only for exact-case names and an excludes file with no include lines.

## Threat model (short)
- Assets: plaintext secret files (.env and similar) under the backed-up ~/Documents folders. OAuth tokens in tokens.json are not in backup_paths.txt (checked; names only).
- Trust boundary: local disk to the Google Drive File Provider folder (DEST_ROOT). Anything rsync writes there goes to Google.
- Entry points that write to Drive: `BackupStatusCard.run_single_folder` (main.py:2612, direct rsync), and `run_backup`, `run_dry_run`, `run_delete_preview` plus `--run-backup` (main.py:39-40, 2713-2785), which all run backup_to_gdrive.sh. A grep of main.py, lab_health.py, workspace*.py and verify.py found no other rsync, cp or ditto into CloudStorage.
- Untrusted or editable inputs: backup_folders.txt, gdrive_backup_excludes.txt (the app's Excludes dialog writes it, main.py:2235), secret_name_patterns.txt, backup_to_gdrive.sh (parsed).

## What holds (evidence)
- Filter order: rsync uses the first rule that matches. The order is: `--include=*.example/*.sample/*.template`, then `--exclude-from=excludes`, then `--exclude-from=secrets` (backup_filter.py:33-37). This matches the script's RSYNC_OPTS (backup_to_gdrive.sh:44-54). The keep-includes only match names ending in .example, .sample or .template. A directory such as `cfg.example/` is included, but its contents still go through the filter: in a probe, `cfg.example/.env` was not copied.
- Fail closed: a missing or empty secret list, a missing excludes file, a missing script, a script that has drifted, or an unknown `$VAR` each raise FilterError, and rsync is not started (tests parametrised over 5 cases). Separately checked: rsync 3.5.1 with a missing `--exclude-from` file exits with code 11 and copies nothing.
- The app always runs its own hard-coded `expected_filter_args`, never the parsed script args (backup_filter.py:100-105). A parse that is fooled can therefore never weaken the app's own rsync. It can only make the drift check pass wrongly (see P3-2).
- Folder names cannot inject rsync options: the source and destination always start with "/", and rsync only reads remote `host:` syntax when the colon comes before the first slash.
- Tests are hermetic. BACKUP_DIR, DOCS, DRIVE_ROOT and DEST_ROOT are monkeypatched to tmp_path. QProcess is replaced by FakeProcess. The real rsync copies only between tmp_path folders. File contents are "dummy". Nothing touches the network. One test (`test_live_backup_script_filters_like_the_app`) reads the live script and the live pattern-name file, read-only.
  `../../../.venv/bin/python -m pytest tests/test_backup_filter.py -q` -> `.............  [100%]` (13 passed).
- No new dependencies (backup_filter imports only the standard library). pip-audit is not installed, so the dependency audit was not run.

## Findings

### P2-1: Secret names in other letter cases reach Drive (both paths)
- Where: secret_name_patterns.txt (outside the repo, case-sensitive list); backup_filter.py:121,125,127 (`fnmatchcase`, so Preview has the same blind spot and does not flag it).
- Scenario: APFS is case-insensitive, so a file stored as `.Env` is the file dotenv opens as `.env`. rsync is case-sensitive, so `.Env` matches neither `.env` nor `.ENV`. Probe with the live pattern files, dummy files, scratch destination:
  `rsync -rlt --include='*.example' --include='*.sample' --include='*.template' --exclude-from=<live excludes> --exclude-from=<live secrets> src/ dst/`
  Copied: `.ENVRC  .Env  .Env.local  ENV.LOCAL  Prod.Env`. The `.env` and `.env.local` dummies were written into the same files as `.Env` and `.Env.local`, which shows the APFS aliasing. Preview: `first_match(rules,'.Env')` -> None and `'Prod.Env'` -> None, so Preview does not list them either.
- Live exposure today: none. A names-only walk of the 6 backed-up folders (56,388 files, using the filter's own rules) found 0 case variants that rsync would copy.
- Impact: a mixed-case secret file is copied to Google Drive in plaintext, and Preview gives no warning.
- Fix: rsync has no case-insensitive match, so write the patterns as character classes (`.[eE][nN][vV]`, `*.[eE][nN][vV]`, ...) in secret_name_patterns.txt (shared with backup_secrets.sh, which must agree). Or have the app run a case-insensitive pre-scan and refuse to start. Add a test with a `.Env` file in a case-sensitive tmp volume, or by asserting the pattern list.

### P2-2: An include line in the editable junk file overrides the secret list
- Where: backup_filter.py:33-37 (junk file comes before secrets); main.py:2234-2235 (`ExcludesDialog.save` writes the editor text as-is); backup_to_gdrive.sh:50-51 (same order).
- Scenario: rsync honours `+ ` lines in `--exclude-from` files. A line such as `+ .env*`, `+ *` or `+ config/**` in gdrive_backup_excludes.txt (typed in the app's Excludes dialog) matches before the secret list. Probe: live excludes file plus `+ .env*`, then the live secret list -> `./cfg.example/.env` copied. Preview treats `+ ` as include (backup_filter.py:133-134), so it shows the file as copied but does not mark it as a secret. rsync_filter_args does not check the excludes file's contents.
- Impact: one edit in the UI silently disables the secret filter for every Drive path.
- Fix: put the secret list before the junk file (keep-includes, secrets, junk) in both the script and `expected_filter_args`. Or fail closed (and refuse to save in the dialog) when the excludes file has `+ `, `!` or other rule-prefixed lines. Add a test.

### P3-1: Trailing whitespace makes Preview and the empty-list check disagree with rsync
- Where: backup_filter.py:48 (`raw.strip()`).
- Probe: a pattern file with `.env ` and `*.env<TAB>` -> rsync copied `a/.env` and `b.env`, while Preview's first_match reported both as secret-excluded. The non-empty check also passes on such a file.
- Live: `grep -c '[[:space:]]$'` on both live pattern files -> 0. Latent only.
- Fix: in the secret list, treat lines with leading or trailing whitespace as a FilterError instead of stripping them.

### P3-2: Drift-check blind spots (the app path itself is unaffected)
- Where: backup_filter.py:61-73.
- Only the first `RSYNC_OPTS=(` block is read. A later reassignment, prepend or `+=`, any `-F` or `--files-from`, and the script's real `SCRIPT_DIR` value (forced to backup_dir) are invisible. Probe: a scratch copy of the live script with `RSYNC_OPTS=(--include='.env*' "${RSYNC_OPTS[@]}")` added after the block -> `script_filter_args(...) == expected_filter_args(...)` -> True. So the check can say "in sync" while the scheduled script leaks. The one-folder path is still safe because it uses its own list.
- Fix: also fail if RSYNC_OPTS is assigned more than once or `--include` or `-F` appears outside the block. Or document that the check covers only the first block.

### P3-3: Parse errors other than FilterError escape the handlers
- Where: backup_filter.py:40-48, 67, 70; main.py:2620-2629 (catches only FilterError); main.py:2245-2247 (catches only OSError).
- Probe: unbalanced quote in RSYNC_OPTS -> `ValueError No closing quotation`; non-UTF-8 byte in the secret list -> `UnicodeDecodeError`. `EXCLUDES= # c` would raise IndexError.
- Impact: still fail closed (rsync is never started), but the user sees no message, only a traceback, and Preview aborts.
- Fix: wrap these in FilterError inside backup_filter.

### P3-4 (pre-existing): Folder name not confined to ~/Documents or the Drive backup folder
- Where: main.py:819 (`DOCS / folder`, `DEST_ROOT / folder`).
- Probe (string building only, no rsync): `/etc` -> src `/etc/`, dest `/etc/`. `../Desktop` -> `~/Documents/../Desktop/` to `.../Backups/MacBook/Documents/../Desktop/`. Python's `/` drops the base for an absolute name, while the script concatenates strings (`$SRC_ROOT/$folder`), so the two paths behave differently. The input is backup_folders.txt, which only the owner edits (the add-folder picker stores `relative_to(DOCS)`, main.py:2996), so exploiting this needs local write access.
- Fix: reject absolute names and `..`, and require `resolve().is_relative_to(DOCS)`.

### P3-5 (scope note, not a regression): coverage by name only
- Neither path covers `*.pem`, `*.key`, `id_rsa*`, `*.p12`, `credentials*.json`, `service-account*.json`, `.npmrc`, `.pypirc`, `.netrc`. `*.example`, `*.sample` and `*.template` are always copied, even if someone puts real values in them. The owner should decide whether secret_name_patterns.txt should grow. Not verified whether any such files exist.

## Test gaps
No test for case variants (the fixture deliberately leaves out `.ENV`), for `+ ` lines in the junk file, for whitespace in patterns, or for non-FilterError exceptions. Mutation check not run by this reviewer.

---

## Author's follow-up (2026-11-20, not part of the review above)

Fixed in the app after the review, each with a test and a hand mutation check (4 of 4 killed);
full suite 259 passed, 1 skipped (`test_appkit_guard`: no `lab_hub` beside a worktree):

- **P2-2, app side:** `rsync_filter_args` refuses to run when `gdrive_backup_excludes.txt` has a `+ `
  include or a `!` line, and the Excludes dialog refuses to save one. The script still reads the junk
  list first; reordering it (secret list before junk list) is a change in `_Admin/backup`, outside this
  repo.
- **P3-1:** pattern lines keep their spaces, as rsync does (checked: rsync copied `a.tmp` past
  `*.tmp␠`), so Preview matches agrees with rsync.
- **P3-3:** `ValueError`, `IndexError` and `UnicodeDecodeError` become `FilterError`, so the user gets
  the "Backup not started" message; Preview matches handles an unreadable secret list.

Open, for the owner (outside this repo or a policy call): P2-1 letter case in
`secret_name_patterns.txt` (character classes such as `.[eE][nN][vV]`; no such file exists today);
P2-2 script-side ordering; P3-2 parse only the first `RSYNC_OPTS` block; P3-4 `backup_folders.txt`
entries that are absolute or contain `..`; P3-5 wider secret list (already TODO, audit L3–L5).
