# Security review: secrets vault (security-engineer), 2026-10-21

Lab root b32ae1b, git_autosync d2c97a6. **No P0/P1.** Fake homes only; no real value read.
Saved by the orchestrator (reviewer is read-only).

P2, all fixed after with tests: (1) `.envrc`, `env.local`, `config.env.local`, `secrets.env.bak`
and upper-case spellings reached Google and missed the bundle — one shared, wider list
(`secret_name_patterns.txt`) now drives both; (2) `.git/objects` carried credential-file blobs
written by git_autosync's snapshot `git add -A` before filtering — credential names are now kept
out of the temporary index by pathspec (history blocked by the gate stays in `.git`, which goes
to Drive; sentinel's findings are allowlisted test fixtures); (3) the purge missed archived app
data and could delete outside Backups/MacBook (a newline in a name; a symlinked parent) — now
`find -P … -delete`, symlink-free resolved paths only, archive included; (4) restore-secrets.sh
wrote anywhere under `~` — now only `~/Documents/` and `~/Library/Application Support/`; (5) until
`opaque1337` is mounted, secrets have no new backup — owner signs in and confirms one bundle
**before** running the purge.

P3 fixed: symlink entries in a bundle refused; `install -m 600`; a symlinked vault path or one
inside Google Drive/Dropbox refused. Noted: a real key saved as `*.example` is copied by design;
symlinked `.env` files are not followed.
