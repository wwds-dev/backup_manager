# Docs audit: spec `more-storage-providers` (Foundry phase 9)

Date 2026-11-20. Branch `claude/docs-more-storage-providers` at 85ff446 (feature tip). Docs only; no `.py`
or test changed. Playbook `tech-writer.md`: `last-reviewed: 2026-10-14`, `status: current`, not stale.
No CHANGELOG file exists (app-context says changes live in TODO and spec logs); none created.

## What changed
- `README.md`: Storage section rewritten (provider table, Proton link-only tile, "total not reported",
  per-tile links, Google Drive split, Cloud accounts wording), new "One-time OneDrive setup", Overview gauge
  note (fifth OneDrive gauge), "does NOT do" line, config-file table (`app_credentials.json`, `tokens.json`,
  `manual_accounts.json`, new `quota_history.json` row), module table row, test-file list.
- `TODO.md`: feature done item (release "not released"), Document pass closed, open items for the two live
  checks, review P3-5 leftovers, Box/pCloud later specs. Secure item untouched.

## Verified against code
- Registry, labels, URLs, Proton text, no-quota flag: `cloud_quota.py:577-619`; `web_link` and the Google
  `?authuser=` rule (plain email, URL-encoded): `cloud_quota.py:629-637`.
- OneDrive scope `Files.Read offline_access`, public client (no secret), `state` check, PKCE, error text:
  `cloud_quota.py:456-521`; stored entry has `provider: "onedrive"`: `:520`; rotation stored: `:540-542`,
  `_store_refresh_token` `:153-164`; total 0/non-numeric -> 0, absent -> None: `:560-574`.
- Credentials form is built from the registry; the OneDrive field is "OneDrive Client ID:" with a
  **Save credentials** button: `cloud_quota.py:605-609`, `main.py:2280-2315`; button "☁ Cloud accounts…":
  `main.py:2178`.
- Add Account lists quota providers plus "Proton Drive (link only, no quota)" with no sign-in:
  `main.py:2444-2449`, `:2481-2484`.
- Tile text "unlimited plan" only for absent total, "total not reported" for 0: `main.py:1980-1985`.
- Split lines, wording, tooltip, hidden unless valid, trash not subtracted: `main.py:1830-1845`,
  `cloud_quota.py:73-86`; Google reads `usageInDrive`/`usageInDriveTrash`: `cloud_quota.py:339-346`.
- History keys `drive`/`trash` optional: `main.py:1311-1319`.
- Links: Finder when mounted else registry page: `main.py:1748-1764`; iCloud link `:2050-2055`.
- Proton: no bar/number `main.py:1851-1856`; mount prefix `ProtonDrive` from registry; no gauge and OneDrive
  gauge only while a tile exists: `main.py:5253`, `:5360-5372`.
- Tests exist for each claim (`tests/test_drive_split.py`, `test_onedrive.py`, `test_tile_links.py`,
  `test_provider_registry.py`; names listed by `grep "^def test"`). The test suite was not re-run here.

## Unverified (marked so in the README)
- Entra portal steps and wording, "Mobile and desktop" platform, personal-account tenant need, admin consent,
  and that Microsoft ignores the port on `http://localhost` (spec 1b: from memory, "re-check at Architect";
  the Architect section records no re-check).
- Google `authuser=` behaviour; whether `usageInDrive` includes trash; the split formula on a real account.
- `Files.Read` being wider than Google's scope (spec says memory).
- Not done: no OneDrive sign-in, owner's real `storageQuota` not read, app not built, no screenshot.

## Open (not fixed here: would edit `.py`)
- Stale copy (review P3-2), **docstrings fixed afterwards on owner's "docs-only" go-ahead** (`cloud_quota.py` module docstring, `AddAccountDialog` docstring in `main.py`; no string shown in the UI changed). The two displayed strings (`main.py:2293` Cloud Accounts text, `:2437` Add Account label) were reworded afterwards on the owner's yes. Original finding: `cloud_quota.py:2-6,22` docstring says Google and Dropbox only and that
  Proton/iCloud "fall back to local disk free space" (contradicted by the last-known fallback and the Proton tile);
  `main.py:2426` docstring and `:2436-2439` AddAccountDialog text say "Google Drive or Dropbox";
  `main.py:5-8` header comment. This is displayed text in part, so left for Secure/Build.
- `main.py:2289-2293` Cloud Accounts text says "Client ID/Secret or App Key/Secret"; OneDrive has no secret.
- No CHANGELOG file and no version bump decided (TODO has the open item); README test-count not stated.
- Onboarding gap: the in-app Documentation viewer does not list the OneDrive setup; README is the only place.

## Update after Secure and Verify-gap fixes (2026-11-20, feature tip f050c9d)
Docs only; no `.py`, test or `docs/legal` file changed. Playbook still `last-reviewed: 2026-10-14`, `status: current`.

### What changed
- `README.md`: new "Sign-in safety" note under the Cloud accounts bullet; config-file table (modes 600 for
  `app_credentials.json` and `manual_accounts.json`, `quota_history.json` marked not locked down, a paragraph on the
  0700 folder and atomic writes); Tests section (conftest isolation and its gap; `test_oauth_hardening.py` listed).
- `SECURITY.md`: first paragraph only (0700 folder, 0600 credential and manual-accounts files written atomically,
  `state`, PKCE, loopback listener). Nothing else touched; no legal conclusion.
- `TODO.md`: duplicate open Secure item and the open "Review P3-5 leftovers" item removed (both fixed); the done Secure
  item now says "not released", 507 tests, PKCE and live sign-in not tested; new open item for the suite writing the
  live `quota_history.json` and `state.json`. Open items kept: P3-3, P3-4, P3-5, quota history mode, stale copy, double
  history read.
- No earlier README text claimed Google/Dropbox lacked `state`, 0644 or body text; nothing contradicted needed removing.

### Verified against code
- `state` (`token_urlsafe(32)`) and `_redirect_code` with `compare_digest`: Google `cloud_quota.py:306,316,319`,
  Dropbox `:392,401,404`, OneDrive `:520,529,532`; `_redirect_code` `:491-499`.
- PKCE S256: Google `:314-315,329`, Dropbox `:399-400,414`, OneDrive `:527-528,541`.
- Listener binds `127.0.0.1` only `:287` (`_ReusableHTTPServer(("127.0.0.1", port), Handler)`); `ThreadingHTTPServer`,
  daemon threads `:224-229`; 5 s handler timeout `:233,261`; request without `code`/`error` gets 404 and the wait continues
  `:266-269`; first response wins `:270-274`.
- Error text: `_oauth_error_text` `:502-510` (status plus a short `[A-Za-z0-9_.-]` code); used at `:332,417,545`.
- Folder 0700 and chmod on every write `:99-102`; `save_app_credentials` `:109-110`, `save_manual_accounts` `:190-191` and tokens
  `:145` all use `_write_json_atomic` (mkstemp, fchmod 0600, os.replace) `:113-125`.
- `tests/conftest.py:8-16` patches `SECRETS_DIR`, `CREDENTIALS_FILE`, `TOKENS_FILE`, `MANUAL_ACCOUNTS_FILE`; `main.py:1200` (`_STATE_FILE`)
  and `:1297` (`_QUOTA_HISTORY_FILE`) are not patched; quota history is written with plain `write_text` `main.py:1325`.
- `tests/test_oauth_hardening.py` exists (20 test functions by `grep`).

### Not verified
- Google's acceptance of PKCE for the Desktop client type: not verified (no live sign-in). No live Google, Dropbox or OneDrive
  sign-in was run. The suite was not re-run here (spec fix logs say 507 tests, 0 failures, exit 139 at Qt teardown).
- That the suite actually writes the live `quota_history.json` and `state.json` was not run; it follows from the unpatched paths.
- The resulting file and folder modes were read from code, not checked on a disk; the spec's tests cover them under umask 022.
- The README line giving 5 seconds and the 404 behaviour rests on the code and the spec's loopback tests, not a manual run.

### Still open
- TODO still has an older open "Document pass for more storage providers" item (README done earlier; CHANGELOG and version remain
  an owner decision; no CHANGELOG file exists).
- Review P3-2 stale copy remains an open code item.
