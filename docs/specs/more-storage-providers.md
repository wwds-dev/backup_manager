# More storage providers, and a Drive / Photos split

Status: **Define, awaiting the owner's gate.** Nothing is built. Written 2026-11-20.

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
- A provider page cannot pick the account: the label says "provider page", not the account. Opening goes
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
5. Proton: add the link-only tile with no quota (1c)?
6. Quick-access links on every tile as in 1d?
