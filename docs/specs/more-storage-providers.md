# More storage providers, and a Drive / Photos split

Status: Define approved by the owner 2026-11-20 ("Approve"). **Architect section below awaits the owner's gate.** Nothing is built.

**Problem.** (1) Add Account offers only Google Drive and Dropbox. The owner wants more known
providers whose quota a public API really returns. (2) The Google tile shows one number; the owner
wants the split between Drive files and Photos.

**User.** The owner, reading Overview and the storage tiles.

## 1. Provider assessment

Facts marked (docs) were read on 2026-11-20; (memory) are from the author's knowledge and must be
re-checked against the vendor docs at Architect before any code relies on them.

| Provider | Quota call | Auth | Verdict |
|---|---|---|---|
| **OneDrive** | `GET https://graph.microsoft.com/v1.0/me/drive?$select=quota` returns `quota.total`, `used`, `remaining`, `deleted`, `state` (docs: learn.microsoft.com/graph/api/resources/quota). Personal and work/school accounts. | OAuth 2.0 code + PKCE, **public client, no secret**; scopes `Files.Read offline_access` (memory; Files.Read is the least privilege that reaches `/me/drive`, wider than Google's metadata-only scope: a Secure-phase point). Refresh token is returned again on refresh and must be stored (memory). Loopback `http://localhost` redirect ignores the port (memory). | **Build first.** Real API, no secret to protect, mounts as `OneDrive-*` in CloudStorage so the existing mount path works. Caveat: work accounts may need tenant admin consent; docs note quota can include system-used space, so "used" is what OneDrive reports, not a file sum. |
| **Box** | `GET https://api.box.com/2.0/users/me?fields=space_used,space_amount` (memory) | OAuth 2.0 with client secret; **refresh tokens are single-use and rotate** (memory): two overlapping refreshes (the accepted overlap in `quota-off-ui-thread`) can invalidate the stored token and force a reconnect. Needs a per-account refresh lock. | **Second, optional.** Works, but costs a lock and a custom app with a secret. Unlimited plans report a huge `space_amount`; must render as unlimited. |
| **pCloud** | `GET /userinfo` returns `quota`, `usedquota` (memory) | OAuth 2.0; the token endpoint host depends on the account's data region (US `api.pcloud.com`, EU `eapi.pcloud.com`), returned with the redirect (memory); the access token does not expire, so no refresh token. | **Third, optional.** Simple once the region is handled. Stores a long-lived token: revocation is manual in pCloud. |
| **Yandex Disk** | `GET https://cloud-api.yandex.net/v1/disk/` returns `total_space`, `used_space`, `trash_size` (memory) | OAuth, scope `cloud_api:disk.info`, client secret | **Not recommended.** Works technically; a Russia-based service for an EU/Irish owner is a legal and trust call that is the owner's, not an agent's. Build only if the owner asks. |
| **MEGA** | none public | The SDK needs the account password to derive keys | **No.** Storing a password breaks the secrets rules. |
| **Proton Drive, iCloud** | none public (already established) | | **No.** Unchanged. |

**Recommendation:** build OneDrive now; Box and pCloud only if the owner has accounts there (ask).
Do not build Yandex or MEGA.

**What the owner must do for OneDrive (cannot be done for them):** sign in at entra.microsoft.com ->
App registrations -> New registration; name "Backup Control Center"; supported account types
"Accounts in any organizational directory and personal Microsoft accounts"; platform "Mobile and
desktop applications", redirect `http://localhost`; API permissions: Microsoft Graph, Delegated,
`Files.Read` and `offline_access`; copy the Application (client) ID. No client secret. A personal
Microsoft account may first need a free Entra tenant (the portal offers it). Box: custom app, OAuth 2.0
user authentication, redirect `http://localhost:53789/`, copy client ID and secret. pCloud: my_apps page,
register the redirect, copy app key and secret.

### 1b. OAuth app the owner must register, per provider

All rows are from memory unless marked (docs); **re-check every row at Architect** against the vendor
docs, and re-check that all of them accept the app's loopback redirect.

| Provider | Register at | App type / auth | Minimum scope for quota | Redirect | Cost / review |
|---|---|---|---|---|---|
| Google Drive (today) | console.cloud.google.com | OAuth client "Desktop app" + secret | `drive.metadata.readonly` (in use) | any loopback port | free; consent screen in testing mode |
| Dropbox (today) | dropbox.com/developers/apps | Scoped app, PKCE + secret | `account_info.read` (in use) | `http://localhost:53789/` registered | free |
| **OneDrive** | entra.microsoft.com -> App registrations (portal.azure.com works too) | **Public client** "Mobile and desktop", PKCE, **no secret** | Graph delegated `Files.Read` + `offline_access` | `http://localhost` (port ignored) | free; personal MS account may need a free Entra tenant; work accounts may need admin consent; no store review for own use |
| **Box** | app.box.com/developers/console -> Create app -> "Custom App" -> "User Authentication (OAuth 2.0)" | confidential client: client ID + **secret** | read access (the default "Read all files and folders") covers `users/me` | `http://localhost:53789/` entered in the app | free developer app; own account only needs no review; some Business accounts need the admin to authorise the app |
| **pCloud** | docs.pcloud.com -> "My apps" (my.pcloud.com/#page=register_app) | OAuth 2.0 code flow, app key + secret; no PKCE, no refresh token (long-lived access token) | none to pick; read access to account info | redirect URI registered on the app | free; token endpoint host is US or EU by account |
| **Yandex Disk** (not recommended) | oauth.yandex.com/client/new | web-services app, client ID + secret | `cloud_api:disk.info` | `http://localhost:53789/` | free; Yandex may ask for a phone-verified account |
| **MEGA** | none | no OAuth; SDK uses the account password | n/a | n/a | rejected |
| **Proton Drive** | none | no public API | n/a | n/a | no quota possible |

### 1c. Proton Drive without quota

Finding: no public quota API (tried, does not work), so no number can be read. Proposal: add a
**link-only tile**, titled "Proton Drive" with the fixed text "No quota available (Proton has no public
API)", **no bar, no percentage, no gauge slot, and no local-disk number** (the old reason these were
left out was the tile repeating the Local Disk figure; this one shows none). It carries the access links
below, so it is worth its row only as a shortcut. Shown only when a `ProtonDrive-*` mount exists, or the
owner adds it by hand. Recommendation: **add it**, small, cost one registry entry plus a tile variant;
skip it if the owner would rather not see a tile without a bar. iCloud already has its own tile (local
`du` figure, labelled as such) and is unchanged except for the link.

### 1d. Quick access on every tile

Each tile gets one link, from the provider registry, never typed by the user:
- Mounted folder exists: **Open in Finder** (already there; kept).
- No mount (accounts added by hand, or the mount is missing): **Open <provider> in browser**.
- Fixed `https://` URLs in the registry (re-check at Architect): Google Drive `drive.google.com`,
  Dropbox `dropbox.com/home`, OneDrive `onedrive.live.com`, Box `app.box.com`, pCloud `my.pcloud.com`,
  Proton `drive.proton.me`, iCloud `icloud.com/iclouddrive`.
- **Owner decision 2026-11-20: Proton tile yes, quick-access links yes, one link on every tile even with
  several accounts of one provider.** Each account has its own tile and so its own link. For Google the
  link is `https://drive.google.com/?authuser=<account email>` when the tile's account is an email (opens
  that account's Drive; re-check at Architect); other providers cannot pick an account from a URL, so
  their link opens the provider page and the label says "provider page", not the account. Opening goes
  through the existing `run_cmd(["open", url])`; the URL comes only from the registry, never from an API
  response. Applies to tiles without quota too (Proton, iCloud).

## 2. Drive / Photos split

What can be read (docs: Drive v3 `about`, `storageQuota`): `limit`, `usage` (total across all Google
services), `usageInDrive`, `usageInDriveTrash`. The docs do not say Photos or Gmail are inside
`usageInDrive`. The Photos Library API lost its read scopes on 2025-03-31 (docs: Google Photos API
updates) and never had a quota call, so Photos has no number of its own. Gmail and Photos cannot be
told apart by any API.

**Honest design.** Two lines under the Google bar, only when the call returned the fields:
- `Drive files <usageInDrive>` (and `trash <usageInDriveTrash>` shown only when that field is present)
- `Photos, Gmail and other <usage − usageInDrive>`, labelled exactly that, never "Photos".

The second figure is a difference, not a read value; the tooltip says so ("total minus Drive files; the
API does not separate Photos from Gmail"). If `usageInDrive` is missing, or the difference is negative,
neither line shows and the tile keeps today's single number. Whether `usageInDrive` already includes the
trash is not documented: the trash figure is shown separately and is **not** subtracted twice or folded
into the "other" line. A Workspace pooled-storage account has a pooled `limit`; the split is per user, so
the tile adds no claim about the pool. No scope change for Google: the current
`drive.metadata.readonly` already serves `about.get`, so no re-consent.

Verification before Build ships: one read of the owner's real `storageQuota` (with the owner's yes, since
it uses their token) to check that `usageInDrive + other = usage` makes sense for their account.

## Success measure
- OneDrive: Add Account lists it; a fake Graph response `{used, total}` renders "X used of Y"; a mounted
  `OneDrive-*` folder gets the Connect link; token refresh stores the rotated refresh token; a 400/401
  shows the reconnect button; a failed call shows the last known value, never local-disk numbers.
- Split: with `usage`, `usageInDrive`, `usageInDriveTrash` present the tile shows the two lines; with
  `usageInDrive` absent, or the difference negative, it shows neither; the word "Photos" never appears
  without "and other". The last-known sample keeps the split so a failed call shows the old split "as of".
- Proton tile shows no number and no bar; every tile has an Open link (Finder when mounted, else the registry URL); a test asserts no URL comes from outside the registry.
- Quota calls stay off the UI thread; full suite green; new logic mutation-checked.

## Non-goals
Yandex, MEGA, Proton, iCloud quota (a Proton link-only tile is in scope, see 1c); Google Photos API; per-folder or per-file breakdown; retry or backoff;
a generic WebDAV or Nextcloud provider (possible later: RFC 4331 quota, app password, no OAuth).

## Design (proposal, for the owner's gate)
Add Account's provider list and the Cloud Accounts credential form come from one provider registry in
`cloud_quota.py` (label, mount prefix, credential fields) instead of the hard-coded two. Overview gauges
are four fixed slots (disk, Google, Dropbox, iCloud, `main.py:5195`): OneDrive gets a gauge only when an
OneDrive account exists (the row adapts), so the page is unchanged for today's setup.

## Architecture notes (for the Architect gate; GATE: network, secrets, state)
- `cloud_quota.py`: registry; `onedrive_connect/_access_token/_quota`; `provider_for_name` gains
  `OneDrive*`; `quota()` dispatch. Public client: only `client_id` stored in `app_credentials.json`.
- Hard-coded `"Google Drive" if ... else "Dropbox"` at `main.py:1657` becomes a registry lookup.
- `quota()` return grows an optional split (`drive`, `trash`) without breaking the `(used, total)` pair
  the history and gauges read; `quota_history.json` samples gain optional fields.
- Rotated refresh tokens are written to `tokens.json` (mode 0600) on every refresh; write is atomic.
  If Box is built, a per-account lock around refresh is required.
- Threads: the same `CallWorker` path as `quota-off-ui-thread`; no new thread start site.
- Secure phase is **required** (network, secrets, auth): Files.Read scope width, token storage, redirect
  handling, error text that must not echo tokens.

## Phases
Define (this file, GATE) -> Architect (GATE) -> Plan -> Build (tests first) -> Review -> Verify -> Secure
-> Document (README provider list and setup, TODO) -> Comply (privacy note lists Microsoft as a
processor of the owner's own token; legal sign-off is the owner's) -> Release (owner's yes). Design
skipped: detail text only. Launch skipped (public tier, optional).

## Open questions for the owner
1. OneDrive now; do you also have Box or pCloud accounts worth building?
2. Wording for the split: "Drive files" and "Photos, Gmail and other"?
3. May one agent read your Google `storageQuota` once (your token) to check the formula?
4. Gauges: add one only when that provider has an account (proposed)?
5. Proton link-only tile (1c): **yes** (owner, 2026-11-20).
6. Quick-access links on every tile (1d): **yes**, per tile for several accounts (owner, 2026-11-20).

## Architect (2026-11-20; GATE: network, secrets, state)

Read first: `cloud_quota.py`, `StorageTile` (`main.py:1633-1900`), `StorageCard.refresh` (`:2100`),
`OverviewPage.refresh_gauges`, the existing tests that patch `cloud_quota.quota`.

### Decisions
1. **Provider registry** in `cloud_quota.py`: a dict `PROVIDERS[key] = Provider(label, mount_prefix,
   web_url, credential_fields, connect, quota, has_quota)`. Keys: `google`, `dropbox`, `onedrive`,
   `proton` (`has_quota=False`), later `box`, `pcloud`. Replaces: `provider_for_name`'s if-chain, the
   `"Google Drive" if ... else "Dropbox"` at `main.py:1657`, `connect()`/`quota()` dispatch, the
   Add Account combo and the Cloud Accounts credential rows. `iCloud` stays its own tile class and gets
   only the link. Registry URLs are literals in the module; nothing from an API response is ever opened.
2. **Quota result keeps the 2-tuple contract.** `quota()` returns `Quota`, a `tuple` subclass
   `(used, total)` with optional attributes `.drive`, `.trash` (None unless read). `used, total = result`
   and every existing test that patches `cloud_quota.quota` with a plain tuple keep working; the tile reads
   `getattr(result, "drive", None)`. Chosen over a dict or a 4-tuple because those break ~20 call sites and
   tests for no gain.
3. **Split rule is Qt-free and tested alone:** `drive_split(used, drive, trash)` returns
   `(drive_files, other, trash)`; `other = used - drive` only if `drive` is not None and `0 <= drive <= used`,
   else `None`. Trash is passed through untouched, never subtracted. The tile renders from it; an invalid
   split renders nothing extra.
4. **History:** `_append_quota_sample` adds optional `drive` and `trash` keys; `_last_known_quota` keeps
   returning `(used, total, ts)` and a new `_last_known_split` reads the same newest sample, so a failed
   call shows the old split "as of" with the old totals. Old samples without the keys are valid. No file
   format version; readers ignore unknown keys.
5. **OneDrive flow** reuses `_wait_for_redirect` and the `REDIRECT_URI` (`http://localhost:53789/`; Entra
   matches any port on a registered `http://localhost`). PKCE via the existing `_pkce_pair`, no secret.
   Authority `login.microsoftonline.com/common/oauth2/v2.0`. `state` parameter: **new**, generated and
   checked on the redirect (the current Google/Dropbox flows send none; adding it for all providers is in
   scope for Secure, see below).
6. **Refresh-token rotation:** `_store_refresh_token(account_key, new_token)` writes `tokens.json`
   atomically (temp file in the same dir, `chmod 0600`, `os.replace`) under one module `threading.Lock`
   shared by all token writes; called whenever a refresh response carries a new `refresh_token`. A per-account
   lock around the whole refresh-then-store is required for Box and is reused by OneDrive (cheap). Overlapping
   fetches therefore cannot interleave a read of `tokens.json` with another's write.
7. **Link-only tiles (Proton) and links:** `StorageTile` takes `has_quota` from the registry; when False it
   never calls `set_usage` network or disk paths: fixed text "No quota available (Proton has no public API)",
   bar hidden, `pct` stays None, and `refresh_gauges` skips it. One link button per tile (each account its own) from
   `registry.web_url` (Google: with `authuser=<email>`, email URL-encoded) when not mounted; "Open in Finder" when mounted (unchanged).
8. **Gauges:** the four fixed slots stay; OneDrive adds a fifth only when a OneDrive tile exists. `Gauge`
   grouping already keys by `tile.provider`; the grid builds the extra column on `refresh_gauges` first run
   and on account add. Proton never gets a gauge.
9. **Threads:** unchanged: one `CallWorker` per tile via `replace_worker`; the OneDrive account-name call (if
   any, for the account line) runs in the same worker like `dropbox_account_email`. No new `start()` site;
   `tests/test_thread_lifetime.py` guards it.

### Data and state
`app_credentials.json` gains `onedrive: {client_id}` (no secret). `tokens.json` entries gain
`provider: "onedrive"`. `manual_accounts.json` unchanged. `quota_history.json` samples gain optional keys.
No new file, no new boundary: **no ADR**; this section is the record.

### Build order (tests first, one commit each)
1. `drive_split` + `Quota` + history keys + tile split lines (Google only; no new network).
2. Registry refactor behind the existing two providers (behaviour unchanged; existing suite is the guard).
3. OneDrive (connect, refresh with rotation, quota, mount prefix `OneDrive`, gauge).
4. Proton link-only tile and links on every tile.
Box and pCloud are separate later specs if the owner asks; the registry makes each one entry plus its flow.

### Risks
- Entra tenant/admin-consent failure for a work account: error text shown, never a token.
- A refresh that returns 400 after rotation lost the token: existing "Token expired, reconnect" path applies.
- Gauge grid change touches `OverviewPage`; covered by `test_overview.py` plus a new test.

### Secure phase (required, after Review)
Scope width of `Files.Read`; `state` check and its rollout to Google and Dropbox; loopback listener is
bound to `127.0.0.1` only (already); atomic 0600 token writes; no token or code in error strings or logs;
registry-only URLs opened.

## Architect approval
Approved by the owner 2026-11-20 ("Approve"). Build may start.

## Build log (2026-11-20, engineer session, branch `claude/wizardly-payne-caa30e`)

Spec, Define and Architect approvals came from `claude/zealous-burnell-c2116b` (merged here, docs only).
Four commits, tests first, in the Architect's build order:

| Step | Commit | What | Tests |
|---|---|---|---|
| 1 | `cc8576e` | `drive_split`, `Quota` tuple subclass, optional `drive`/`trash` history keys, `_last_known_split`, Google tile lines "Drive files … · trash …" and "Photos, Gmail and other …" (tooltip: total minus Drive files) | `tests/test_drive_split.py` |
| 2 | `ee0b4cc` | `PROVIDERS` registry: `provider_for_name`, `connect`/`quota`/`account_email` dispatch (late-bound by name), Add Account combo, credential form (save now keeps unknown keys), tile label | `tests/test_provider_registry.py` |
| 3 | `698500a` | OneDrive: PKCE public client, no secret, `state` (32 bytes, `compare_digest`) checked before the code is exchanged; token-endpoint errors show only the OAuth error code; refresh under a per-account lock, rotated token stored via atomic write (`mkstemp` in the same dir, `fchmod 0600`, `fsync`, `os.replace`) under one `_TOKENS_LOCK` that all `tokens.json` writes now use; Graph `/me/drive?$select=quota`; mount prefix `OneDrive`; fifth Overview gauge only while a OneDrive tile exists | `tests/test_onedrive.py` |
| 4 | `60a66fd` | Proton and iCloud in the registry with `has_quota=False`; Proton tile (mounted or added by hand, no OAuth): fixed text, bar hidden, `pct` None, no Connect, no gauge; one Open link per tile: Finder when mounted, else registry URL (Google `?authuser=<email>` only for a plain email, URL-encoded), fixed at construction | `tests/test_tile_links.py` |

**Suite:** `.venv/bin/python -m pytest -q -p no:warnings --junitxml=…` → tests=455, failures=0,
errors=0, skipped=1 (was 392 before step 1). The process exits 139 after the last test; the same
exit happens on the base commit `d22d4c2` before any of this work (Qt teardown at interpreter
exit, pre-existing), so results are read from the JUnit XML, not the exit code.

**Mutation check (by hand, 16 mutants, all killed):** split upper bound removed, lower bound
removed, trash subtracted, label "Photos" alone; rotated token not stored, non-atomic write,
mode 0644, per-account lock removed, stored entry drops `provider`; state check removed, missing
state accepted; token-exchange error echoes the body; `authuser` not URL-encoded, no email check;
Proton bar shown; OneDrive gauge always present.

**Not done / not verified here:**
- `state` rollout to the Google and Dropbox flows: Secure phase per Architect decision 5, not built.
- The one read of the owner's real Google `storageQuota` (needs the owner's yes) has not run.
- No live OneDrive sign-in: needs the owner's Entra app registration; only fakes were used.
- No OneDrive account-name call (would need `User.Read`); the tile shows the mount or label name.
- App not built or installed; no screenshot.

## Review fix log (2026-11-20, owner: "Fix P2s + tooltip")

Review: `docs/audit/more-storage-providers-review.md` on `claude/nice-agnesi-fa7204`. Tests first, one commit each:

| Finding | Commit | Fix | Test |
|---|---|---|---|
| P2-1 | `2117864` | `_store_refresh_token` writes nothing for an account no longer in `tokens.json`; `disconnect()` holds `_refresh_lock(account_key)` then `_TOKENS_LOCK` (same order as a refresh) | `test_store_refresh_token_never_recreates_a_removed_account`, `test_disconnect_mid_refresh_stays_disconnected` (disconnect from another thread mid-refresh; asserts it waited, the entry stays gone, `is_connected` False) |
| P2-2 | `ea347ef` | `onedrive_quota`: total is None only when the key is absent; 0, negative or non-numeric becomes 0. Tile: None -> "used (unlimited plan)", 0 -> "used (total not reported)", no percentage. Applies to any provider returning 0 | `test_quota_zero_or_unusable_total_is_not_unlimited[0,"0",None,"abc",-5]`, `test_tile_total_zero_says_not_reported`, `test_tile_total_absent_still_unlimited` |
| P3-1 | `914774f` | Tooltip: "Total minus Drive files; Google's API reports no separate figure within Photos, Gmail and other." | `test_photos_never_alone` now checks label and tooltip |

**Mutation check (7 mutants, all killed):** store recreates a removed account; disconnect without the refresh
lock; total 0 -> None; non-numeric total -> None; negative total kept; tile shows "unlimited" for 0;
tooltip "Photos" alone.

**Suite:** tests=464, failures=0, errors=0, skipped=1 (JUnit XML). The process still exits 139 after the
last test in this worktree (the reviewer's scratch run exited 0); pre-existing, see the build log.

Left untouched as instructed: P3-2 (stale copy), P3-3 (double history read), P3-4 (redirect GET), P3-5
(Google/Dropbox `state` and error text), for Secure or later.

## Secure fix log (2026-11-20, owner: "Fix now")

Secure report: `docs/audit/more-storage-providers-secure.md` on `claude/blissful-dewdney-1f30cb`. Tests first
(`tests/test_oauth_hardening.py`), one commit each:

| Finding | Commit | Fix | Test |
|---|---|---|---|
| P2-1 | `af48bb6` | Google and Dropbox send a `state` (`token_urlsafe(32)`) and check it with `_redirect_code` (`compare_digest`) before the code is used; Google adds PKCE S256 (`code_challenge`, `code_verifier` in the exchange) | bad, empty and missing `state` rejected with no exchange (both providers); state differs per attempt; challenge = S256(verifier sent) |
| P2-2 + P3-2 | `c5717a8` | Listener is a `ThreadingHTTPServer` (daemon request threads, never joined on close), handler socket timeout 5 s; a request with neither `code` nor `error` gets 404 and the wait goes on; the first sign-in response wins | real loopback sockets, no provider: a stalled connection does not block the real redirect, does not hold the wait past its timeout, the port rebinds after; `/favicon.ico`, `/`, `/?foo=bar` ignored; `error=` ends the wait; a later response does not overwrite the first (`b618499`) |
| P2-3 | `a9072ff` | `app_credentials.json` and `manual_accounts.json` go through `_write_json_atomic` (mkstemp 0600, fchmod, fsync, os.replace); the folder is created 0700 and chmod 0700 on every write (tightens an old 0755); `_write_json` removed | under umask 022 for all three files: new folder 0700 and file 0600; loose 0755/0644 tightened; the temp file is 0600 with full content before the rename; a failed replace leaves the old file and no temp file |
| P3-1 | `fdbf6ad` | Google and Dropbox token-exchange errors use `_oauth_error_text` (status plus the OAuth error code); the code is shown only if it is a short `[A-Za-z0-9_.-]` word | no description, code or secret in the text; non-JSON body; list, nested, long or spaced `error` fields give just "HTTP 400" |

**Mutation check (16 mutants, 15 killed):** each provider without the state check; Google without
challenge or verifier; single-threaded server; joined request threads; stray request ends the wait;
later response overwrites (killed after `b618499`); folder not chmod / default mkdir mode; credentials or
manual accounts written non-atomically; body echo in either provider; error code unfiltered. Survivor:
removing `os.fchmod(fd, 0o600)` is equivalent (`mkstemp` already creates 0600); kept as belt and braces.

**Suite:** tests=503, failures=0, errors=0, skipped=1 (JUnit XML); the process still exits 139 at
teardown (pre-existing).

Left untouched as instructed (to TODO): Secure P3-3 (disconnect can block the UI up to ~20 s), P3-4
(connect and an in-flight refresh can overwrite each other), P3-5 (stored numbers not range-checked),
P3-6 (quota history written 0644, non-atomic); P3-7 needs no change. Review P3-2 (stale copy) and P3-3
(double history read) also stay open. Not verified: Google's acceptance of PKCE for the Desktop client
type (no live sign-in).

## Secure follow-up fix log (2026-11-20, P3-4, P3-5, P3-6)

P2-1, P2-2, P2-3, P3-1, P3-2 were already fixed above (`af48bb6`..`fdbf6ad`); this session found them on the
branch and added only the rest. Tests first (`tests/test_secure_followups.py`).

| Finding | Fix | Test (mutant killed) |
|---|---|---|
| P3-4 | `_set_token_entry` takes the account refresh lock before the tokens lock | blocks while a refresh holds the lock (lock removed) |
| P3-5 | `used` clamped to >= 0 in Google, Dropbox and OneDrive quota | negative `used` gives 0 (each clamp removed, 3 mutants) |
| P3-6 | `main._append_quota_sample` writes via `_write_json_atomic` (0600, folder 0700) | writer called, file 0600, folder 0700 (plain `write_text`) |

Suite: tests=514, failures=0, errors=0, skipped=1 (JUnit XML). Still open: P3-3 (disconnect can block the UI
up to ~20 s), review P3-2 and P3-3.

## Secure re-check fix log (2026-11-20, R-1, R-2, R-3, from the Secure re-check of b0d4d32)

Report: `docs/audit/more-storage-providers-secure-recheck.md` on `claude/blissful-dewdney-1f30cb`. Tests first
(`tests/test_oauth_hardening.py`).

| Finding | Fix | Test (mutant killed) |
|---|---|---|
| R-1 | `_wait_for_redirect` claims the response under the lock with a `claimed` flag, before answering; `done` is only the signal | a second request while `done` is slow cannot overwrite the first (deterministic; old `done.is_set()` check killed); 12 concurrent requests store exactly one |
| R-2 | `_wait_for_redirect(port, timeout, state=)`: with a state, only a request carrying it (`compare_digest` on bytes) is claimed; others get 404 and the wait continues. The three connect functions pass their state | no/wrong/non-ASCII state and a bare `error=` do not end the wait, the real one does (check removed, 2 mutants); each provider passes its state |
| R-3 | `total` clamped to >= 0 in Google and Dropbox | negative total gives 0 (both clamps removed) |

Without a state (direct callers, older tests) the listener behaves as before. A timeout still reports
"No authorization code received". Suite: tests=520, failures=0, errors=0, skipped=1 (JUnit XML).

## Verify-gap fix log (2026-11-20, Build follow-up for the second Verify pass at 2084ec2)
Test-first, loopback sockets only, no provider call.
- **G1** `test_listener_binds_loopback_only`: mutant `("0.0.0.0", port)` at the bind line FAILS it (restored).
- **G2** `test_silent_connection_is_closed_after_the_handler_timeout` (timeout patched to 0.3 s): mutants `timeout = None` and `timeout = 600` both FAIL it (restored).
- **S1** `_redirect_code` compares `.encode()` bytes, so a non-ASCII `state` is rejected with the normal "state check failed" message; `test_non_ascii_state_is_rejected_cleanly` failed with TypeError before the fix, passes after.
- **S6** `tests/conftest.py` autouse fixture points `SECRETS_DIR`, `CREDENTIALS_FILE`, `TOKENS_FILE`, `MANUAL_ACCOUNTS_FILE` at tmp_path for every test; per-test patches still override it.
- Suite: 507 tests, 0 failures, 0 errors, 1 skipped (503 + 4 new); exit 139 is the known Qt teardown crash. Verify should re-run.

## Third-pass fix log (2026-11-20, residual P3s R1, R2 from the third Verify pass)
- **R1** `test_production_handler_timeout_is_short` pins `0 < _REDIRECT_REQUEST_TIMEOUT <= 10`; mutant `_REDIRECT_REQUEST_TIMEOUT = 600` FAILS it (restored). The comment on the patched-timeout test no longer claims it kills 600.
- **R2** `tests/conftest.py` now also redirects `main._STATE_FILE`, `_QUOTA_HISTORY_FILE`, `_INSTANCE_LOCK_FILE` (icloud_du.log follows `SECRETS_DIR`), in two layers: a session baseline (so an undone per-test patch falls back to scratch, not the live folder) plus the per-test folder. `tests/test_secrets_isolation.py` calls the real writers unpatched. Proof with `HOME` pointed at a scratch dir: function-level layer alone still left `state.json` in the fake live folder (a later write after a per-test patch was undone); with the session baseline the folder stays empty over a full run. Without the `main` patches the isolation test fails.
- Suite: 509 tests, 0 failures, 0 errors (507 + 2 new); exit 139 is the known Qt teardown crash.
- Incident: the red run of the isolation test, written before the fix, executed against the real paths and overwrote the live `state.json` with `{"k": 1}` (previous contents unrecoverable) and appended a test sample to `quota_history.json` (removed again). The owner's app state (preferences, cooldowns) may need re-setting.

## Fourth-pass fix log (2026-11-20, residual P3s from the fourth Verify pass)
- `tests/conftest.py` now also redirects `main.WORKSPACE_REPORT` and `main._SHOW_REQUEST_FILE` in both layers (session baseline + per-test).
- `test_every_secrets_and_state_writer_lands_in_the_test_folder` makes one real-writer call per path (`save_app_credentials`, `save_tokens`, `save_manual_accounts`, `workspace_extra.write_report`, `_SHOW_REQUEST_FILE.write_text`) and asserts each lands under tmp_path. Removing any one of the five redirects from `_redirect` FAILS it (hand-planted one at a time, restored). All runs under a fake HOME.
- Suite under a fake HOME, twice: 510 tests, 0 failures, 0 errors, 2 skipped (509 + 1 new); the fake live folder was empty afterwards; exit 139 is the known Qt teardown crash.
- Incident 2: the red run of the new test was started once with the real HOME by mistake and wrote the live `workspace_report.json` (`{"ok": true}`; the app regenerates it on the next workspace scan; the junk file was removed) and a `show_request` (not present afterwards; the running app consumes it). No other live file was touched (credentials, tokens and manual accounts were already redirected).
