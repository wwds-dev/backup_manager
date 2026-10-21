# Spec: secrets go to an encrypted vault, not to plaintext Google Drive

Status: **Approved by the owner 2026-10-21**: vault on `opaque1337@proton.me`; rotate the keys;
delete the old plaintext copies after a dry-run; no SSH key or gh token backup.
Follows git_autosync's `full-mac-backup` and `restore-and-continue` (both released 2026-10-21),
which left this as "item 4".

## Define

**Problem.** Everything on the Mac is now backed up, but the secrets travel the same way as
everything else, in plaintext:

| Secret | Where it is backed up today |
|---|---|
| `.env` files with live API keys: `sentinel/.env` (nine keys), `imprint/.env`, `imprint/vidforge/.env`, one in `archive/fixes_2026-10-12/…` | Google Drive, daily (`~/Documents/lab` is copied whole; `.env` is not excluded) |
| App data in `~/Library/Application Support/` — Imprint keeps its API keys there (AGENTS.md: "carry the user's keys and database"), plus each app's SQLite database | Google Drive, `Backups/MacBook/Home/` (since 2026-10-21) |
| `~/.ssh/id_rsa` | nowhere |
| gh's token (macOS keychain, `~/.config/gh/hosts.yml`) | nowhere |

Google Drive is not end-to-end encrypted: anyone who gets into that Google account, or Google
itself, can read every key. Google also keeps deleted files in Trash and old versions, so
removing a file from the live copy does not remove it from Google.

**User.** The owner: wants the keys back on a new Mac without copying them by hand, and wants
no readable key anywhere a single account breach could reach.

**Required behaviour.**
1. **A secrets bundle in the Proton Drive vault**, written by the daily backup: every `.env*`
   file under the backed-up folders (excluding `*.example`, `*.sample`, `*.template`) and the
   app-data folders, as one archive with a list of where each file came from. Proton Drive is
   end-to-end encrypted. Kept: the latest bundle, plus the last 7 daily ones.
2. **None of it in Google Drive any more:** `.env*` files are excluded from the Google copy, and
   the app-data folders move from Google to the bundle. `~/.gitconfig` and the LaunchAgent
   plists hold no secrets (checked 2026-10-21) and stay on Google.
3. **The plaintext copies already in Google Drive are removed** — the live files, then Drive's
   Trash — after a preview the owner approves (Decision 3).
4. **Restore puts them back:** `restore-secrets.sh <bundle>` (git_autosync, beside `restore.sh`)
   copies each file back to its recorded path, mode 600, never overwriting a newer file.
5. **SSH key and gh token are not backed up** (Decisions 4 and 5): on a new Mac, `gh auth login`
   and a new SSH key added to GitHub are faster than restoring old ones, and the old ones stay
   revocable.
6. **Every key that sat in plaintext on Google Drive is rotated** (Decision 2): an owner task,
   listed by key name only, never by value.

**Success measure.**
- After one daily run: a scan of `Backups/MacBook/` on Google Drive finds no `.env*` file and no
  app-data folder; the Proton vault holds today's bundle, and its file list matches a fresh
  census of the Mac (same count, same paths).
- Restore drill: `restore-secrets.sh` into a scratch folder gives byte-identical files.
- The rotation checklist in `TODO.md` is ticked off by the owner.

**Non-goals.** A password manager migration. Secrets in git history (gitleaks already blocks
pushes). Encrypting the whole Google Drive copy. The macOS keychain (iCloud Keychain, if on,
already carries it; out of scope either way).

## Proposed Architect (same gate)

- **Bundle:** in `backup_to_gdrive.sh` (run by BCC), a new step builds
  `secrets_<date>.tar.gz` in a mode-700 temp folder: the `.env*` files found under
  `backup_folders.txt` (same excludes), the app-data folders now listed in `backup_paths.txt`
  (databases via `sqlite3 .backup`, as today), and `MANIFEST.tsv` (source path, size,
  sha256). It is copied into the Proton Drive folder at
  `Vault/Credentials-Recovery/Mac-secrets/`, then `latest.tar.gz` is replaced. Bundles older
  than the last 7 are deleted from that folder (Proton keeps its own version history).
- **The Proton folder** is found under `~/Library/CloudStorage/ProtonDrive-<account>-folder`
  (two accounts are mounted; Decision 1). If it is not mounted, the run fails that step loudly
  and still does the Google part; BCC's tile shows "Secrets not backed up".
- **macOS permission:** BCC, not this script, holds the folder permissions. The first run asks
  for access to the Proton folder once; BCC's status says so until it is granted.
- **Google side:** `gdrive_backup_excludes.txt` gains `.env` and `.env.*` (with
  `*.example`/`*.sample`/`*.template` still copied, via rsync include rules); the app-data lines
  move from `backup_paths.txt` to a new `secret_paths.txt`.
- **Cleanup of old copies:** a one-off `purge_plaintext_secrets.sh --dry-run|--apply` lists, then
  deletes from Google Drive, every `.env*` file under `Backups/MacBook/` and `_deleted/`, and the
  `Backups/MacBook/Home/Library/Application Support/` tree. Drive's Trash must then be emptied in
  the Drive web UI, which only the owner can do.
- **Restore:** `restore-secrets.sh <bundle.tar.gz> [--into DIR] [--dry-run]` reads MANIFEST.tsv,
  checks each sha256, and refuses paths outside `~/` or containing `..`.

## Decisions for the owner

1. **Which Proton account holds the vault?** Owner, 2026-10-21: **`opaque1337@proton.me`**.
   It is not mounted on this Mac (only `netrunner55555` and `sapio1337` are), so the owner
   signs it in to the Proton Drive app first; the script then finds
   `~/Library/CloudStorage/ProtonDrive-opaque1337@proton.me-folder` and refuses any other.
2. **Rotate the keys that were in Google Drive in plaintext?** Recommended: yes, every live key
   in the four `.env` files and Imprint's stored keys. Revocation is cheap, and Drive's history
   means they may have been readable for weeks. I list the key names; you rotate them at each
   provider.
3. **Delete the old plaintext copies from Google Drive?** Recommended: yes, after the dry-run
   list. It needs you to empty Drive's Trash afterwards.
4. **SSH key:** recommended: do not back it up; on a new Mac, make an ed25519 key and add it to
   GitHub. Alternative: put `~/.ssh` in the bundle (needed only if other servers trust this
   key).
5. **gh token:** recommended: never backed up; `gh auth login` on a new Mac.

## Build and review (2026-10-21)

Built in the lab root (`_Admin/backup/backup_secrets.sh`, `secret_name_patterns.txt`,
`secret_paths.txt`, `purge_plaintext_secrets.sh`, step 5 of `backup_to_gdrive.sh`) and
git_autosync (`restore-secrets.sh`; snapshots keep credential names out of `.git/objects`).
Security review: no P0/P1, P2s fixed (`docs/audit/secrets-vault-security.md`). Tests: 198 in
git_autosync, including the bundle against a fake home and crafted bundles.

**Order for the owner:** (1) sign `opaque1337@proton.me` in to Proton Drive; (2) after the next
daily run, check that `Vault/Credentials-Recovery/Mac-secrets/latest.tar.gz` exists (BCC's log
says `SECRETS: OK`); (3) only then run `purge_plaintext_secrets.sh`, then `--apply`, then empty
Drive's Trash; (4) rotate the keys listed in `TODO.md`. Until (1), the daily run reports
`SECRETS: FAILED` and the old Google copies are the only copy of the secrets — do not purge first.
