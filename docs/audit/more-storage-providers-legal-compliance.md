# Legal check: spec `more-storage-providers` (Foundry phase 10, Comply)

Status: DRAFT (legal-compliance agent, not a lawyer), 2026-11-20. Tier `public`. Nothing here is signed
off, approved or "compliant"; a person signs. Code state: `HEAD` = `main` = `4288539` (the change is
merged: OneDrive provider, Google Drive / "Photos, Gmail and other" split, Proton link-only tile, per-tile
links, hardened sign-in). Playbook `docs/playbooks/legal-compliance.md`: `status: current`,
`last-reviewed: 2026-11-11` (9 days old; not stale). Rules the playbook states and that I did not re-read
at source are marked "(playbook)". Provider pages were read on 2026-11-20 with WebFetch/WebSearch; where
a page could not be read I say "not verified". The pack is in the private HQ (`docs/legal`, symlink,
git-ignored); I did not run git there.

Inputs read: AGENTS.md, app-context, playbook, the spec, `docs/audit/more-storage-providers-{secure,verify,docs}.md`,
`workspace-cleanup-legal-compliance.md` (format), README, SECURITY.md, SUPPORT.md, LICENSE,
`requirements.txt`, the whole legal pack, and `cloud_quota.py` / `main.py` by grep and targeted reads.

## 1. What the change does, as far as data and third parties go (evidence)
- OneDrive: browser sign-in at `login.microsoftonline.com/common/oauth2/v2.0`, public client (only an
  Application ID is stored), PKCE + `state`, scope `Files.Read offline_access`
  (`cloud_quota.py:484-488,523-542`); quota read: `GET https://graph.microsoft.com/v1.0/me/drive?$select=quota`
  (`:580-584`). Refresh token (rotated by Microsoft) stored in `tokens.json`, mode 0600, atomic
  (`:155-164,561-570`); client ID in `app_credentials.json` (`:605-609`).
- All hosts are literals; full list by `grep -n -o -E "https?://..." cloud_quota.py main.py ...` on
  2026-11-20 is in `privacy.md`. No host of the owner's. The only other outbound call is the user-set
  failure webhook (`main.py:3175-3217`).
- Stored: sizes only (`quota_history.json`: `used`, `total`, optional `drive`, `trash`; 60 samples per
  account, `main.py:1322-1345`); no file names, no Microsoft account name (the spec's build log: no
  `User.Read`).
- Opened in the browser: fixed registry pages; the Google link may carry the owner's own email as
  `?authuser=` (`cloud_quota.py:665-666`).
- `requirements.txt`: `git diff main -- requirements.txt | wc -l` = 0 and, because `HEAD` = `main`,
  `git diff d22d4c2 HEAD -- requirements.txt | wc -l` = 0 (`d22d4c2` is the pre-change base in the build
  log). New imports are stdlib only. No Microsoft SDK. No models (`app-context.md`, `## Models used`: none),
  so no `ai-act.md`.

## 2. Regimes (change from `register.md`)
| Regime | Result | Note |
|---|---|---|
| GDPR / DPA 2018 | No change to the owner's position on the evidence | Role statement and Art. 2(2)(c) reading in `privacy.md` ("Who is the controller?"). Microsoft, Google, Dropbox are independent providers of the user's own accounts; the DPF status of each is **not verified** (the DPF list page could not be searched). Not a legal opinion. |
| DPIA | Not indicated | Zero WP248 criteria; the `Files.Read` token width is a security risk, not a DPIA trigger (`privacy.md`). Rules from the playbook. |
| ePrivacy, CRA, EAA, DSA, PLD, consumer, AI Act, gambling | Unchanged | Still free, non-commercial, no model; `register.md` rows. |
| Licences | No change | Dependency diff empty (section 1); no logos or fonts added (`licences.md` addendum). |
| Service terms of providers | Flagged, not concluded | Section 4. |
| Names of providers | Descriptive; README lacks the disclaimer | Section 3. |

## 3. Provider names: uses, and the README edit (not made by me)
The actual uses (counts per file, kinds of use, no logos) are in `name.md`, "Addendum 2026-11-20".
In short: plain-text names in tile titles, the Add Account list, mount prefixes, link labels and the
README; OneDrive and Microsoft/Entra are new; Box is not used anywhere.

**Does the README have a non-affiliation disclaimer?** No. `grep -n -i "affiliat\|trademark\|not endorsed\|disclaim" README.md`
returns only line 779 (the app's own name). The draft in `terms.md` exists but was never copied and did not
name Microsoft (now added in the pack). Also absent: "Use at your own risk" and a Privacy section.

**Exact README edit proposed (for the owner or tech-writer; not trivial, so I did not edit README):**
replace the `## Licence` section's last two sentences' neighbourhood by adding, directly **before** `## Licence`
(README line 777), these two sections, and keep the Licence section as is:

```markdown
## Privacy
Backup Control Center runs on your Mac. It has no server, no account with us, no analytics and no crash
reporting, and the author receives no data from it. It talks to the services you connect: Google,
Dropbox and Microsoft OneDrive (to read your storage quota, using an OAuth client or app registration
that you create yourself) and, if you set one, a webhook URL (it receives the fixed text "backup
finished WITH ERRORS"; no file names). For OneDrive the app asks Microsoft for the permission
`Files.Read`, which technically allows reading your OneDrive files, but it requests only your storage
quota and stores only sizes. The links on each tile open the provider's own website. On your Mac it
stores, in `~/Library/Application Support/Backup Control Center/`, your OAuth client details,
per-account refresh tokens (plain JSON files readable only by your user, mode 0600; not the macOS
Keychain), quota history, settings and records of the cleanups you ran. Removing an account in the app
deletes only the local token; to revoke access go to the provider (Microsoft:
<https://account.live.com/consent/Manage>, or <https://myapps.microsoft.com> for work or school
accounts). Delete the folder to remove everything the app stores. This describes what the code does at
the version in the window title; it is not a legal document.

## Not affiliated
Backup Control Center is an independent project. It is not affiliated with, endorsed by or sponsored by
Google LLC, Dropbox, Inc., Microsoft Corporation, Proton AG, Apple Inc. or The Qt Company. Google Drive,
Google Photos, Gmail, Dropbox, Microsoft, OneDrive, Entra, Proton Drive, iCloud, Time Machine and macOS
are names or trademarks of their respective owners, used here only to say which service or product the
app talks to or reads about. No logos of these companies are used. Use at your own risk: the software is
provided as is (see `LICENSE`); it can delete or move files, and it reports what your backup logs say;
it does not prove a backup can be restored. Test a restore.
```
Before it goes in: the owner confirms the "no server, nothing sent" claims with a network trace
(`privacy.md`, "Before publishing"); company names (Proton AG, Dropbox, Inc.) are from my knowledge, not
checked against a register today. Further README edits, each tied to a claim in `claims.md`:
1. `:69`, `:465-466` and the UI string `cloud_quota.py:642-644`: replace "Proton has no public API" with
   "no quota API this app can use" (C18).
2. `:136-137`: drop "(unverified)" for the port statement; Microsoft's redirect-URI page confirms it (C33).
3. `:145-146`: replace "per the design notes, not re-checked" with a dated cite of Microsoft's Graph "Get
   drive" page, which lists `Files.Read` as the least-privileged permission (C34).
4. Optional: a Google setup note (README has none) that a consent screen left in **Testing** makes Google
   refresh tokens expire after 7 days (section 4, finding P3-1).

## 4. Provider terms: flagged, not concluded
Sources fetched 2026-11-20. These are the providers' own pages, not legal advice; whether they bind a
user's self-registered personal app, and what follows, is a person's call.

| Provider / document (URL) | Version or date | Point that touches this app | Status |
|---|---|---|---|
| Microsoft APIs Terms of Use (<https://learn.microsoft.com/en-us/legal/microsoft-apis/terms-of-use>) | "Last Updated: October 2025" | s.3(b)(5): do not request more than the minimum permissions: `Files.Read` is Microsoft's documented least-privileged delegated permission for `GET /me/drive` (personal and work), see below. s.3(b)(11): use data only within the permissions the user gave. s.3(e): an app using the OneDrive API "may not enable storage of system data in Microsoft OneDrive", incl. "computer system back-up data": this app only reads quota and its backup goes to Google Drive (`main.py:119-140`), so not engaged; reopen if the rsync target ever becomes OneDrive. s.4: report vulnerabilities and data breaches that relate to the connection to Microsoft APIs to MSRC (secure@microsoft.com). s.5(d)-(e): a written privacy statement, and for Microsoft sign-in a link to <https://account.live.com/consent/Manage> and/or <https://myapps.microsoft.com> to revoke consent. s.11(e): no processor-subprocessor relationship. s.6: Microsoft may change or end the APIs at any time. | Read; applicability to a user's own registration **not decided** |
| Microsoft identity platform Terms of Use (<https://learn.microsoft.com/en-us/legal/microsoft-identity-platform/terms-of-use>) | "Last revised: May 01, 2019" (page updated 2025-10-28) | s.2.1(5): an Application must not use Microsoft trademarks without approval (the app uses the names descriptively; no logos). s.2.1(6)-(7): present users with an EULA and a publicly available Privacy Statement accessible within the Application (the README Privacy section above is the cheapest answer; no in-app link exists today: **not checked in `main.py`**). s.3.1: Display Name must not be "protected by trademark ... or that may cause confusion" (the README tells users to use "Backup Control Center": see `name.md`). s.8.5: no joint-controller or processor-subprocessor relationship. | Read; open |
| Microsoft Graph permission `Files.Read` (<https://learn.microsoft.com/en-us/graph/api/drive-get>, page updated 2026-05-06) | | Least privileged: `Files.Read` for work/school and personal; higher: `Files.Read.All`, `Files.ReadWrite*`, `Sites.*`, `User.Read`. So the width the README admits is not avoidable for `/me/drive`. The permissions-reference entry for `Files.Read` (consent rules, wording) could not be read: the page was too large for the tool. | Least-privilege point verified; consent wording **not verified** |
| Microsoft Entra redirect URIs (<https://learn.microsoft.com/en-us/entra/identity-platform/reply-url>, `ms.date` 2025-05-14, updated 2026-06-15) | | `http://localhost` valid; "the port component ... is ignored" for localhost matching; "Mobile and desktop applications" is the platform for a desktop app; the page also says the IPv6 loopback `[::1]` "isn't currently supported" and prefers `127.0.0.1` over `localhost` (the app registers `localhost` and listens on `127.0.0.1` only, `cloud_quota.py:287`; a Secure question, not legal). | Verified |
| Graph `quota` resource (<https://learn.microsoft.com/en-us/graph/api/resources/quota>, `ms.date` 2024-04-03) | | "In OneDrive Personal, the values reflect the total/used unified storage quota across multiple Microsoft services." Basis for the README's "OneDrive's used number is what OneDrive reports". | Verified |
| Google API Services User Data Policy (<https://developers.google.com/terms/api-services-user-data-policy>) | "Last modified: February 15, 2024" | Applies to apps requesting Google user data; no personal-use exemption stated on the page (only an in-domain exemption for sensitive/restricted scope requirements). Limited-use rules for sensitive/restricted scopes; a published privacy policy is required, and its URL is listed in the OAuth client "when the app is made publicly available". `drive.metadata.readonly` is classed **restricted** by Google (<https://developers.google.com/workspace/drive/api/guides/api-specific-auth>). A personal Desktop client the user creates for themselves is not made "publicly available"; if the owner ever published a shared client, verification and possibly an annual security assessment would apply. | Read; not concluded |
| Google OAuth "Testing" mode (<https://developers.google.com/identity/protocols/oauth2#expiration> and <https://support.google.com/cloud/answer/15549945>) | no date on the pages ("©2026 Google") | A project in Testing is "issued a refresh token expiring in 7 days" (exception: only name, email, profile scopes). The 100-test-users cap applies to unapproved sensitive/restricted scopes; it is per project, and each user of this app makes their own project, so the cap is not reached by design. The code's setup note says "OAuth consent screen (External, add yourself as test user)" (`cloud_quota.py:11`), i.e. Testing. Result: the user's Google token dies after 7 days and the tile shows "Token expired — reconnect"; README and SUPPORT.md do not say why. | Verified; see finding P3-1 |
| Google Drive v3 `about` (<https://developers.google.com/workspace/drive/api/reference/rest/v3/about>) | no date on the page | `usage` "The total usage across all services"; `usageInDrive` "The usage by all files in Google Drive"; `usageInDriveTrash` "The usage by trashed files in Google Drive"; the page does not say whether `usageInDrive` includes trash; `limit` absent for unlimited; for pooled-storage organisations `limit` and `usage` reflect the organisation. Matches the README's "Unverified" wording and the spec's non-claim about pools. | Verified |
| Dropbox Developer Terms (<https://www.dropbox.com/developers/terms>) | "Effective: March 1, 2025" | Contracting entity depends on location (Dropbox International Unlimited Company outside North America). Privacy policy "made available to Users"; use of User Data only as the user authorises; reasonable security and prompt report of known or suspected breaches (s.2); do not suggest Dropbox endorses the app; follow the Developer Branding Guide (s.5.1; guide **not read**). Personal use of the platform not addressed on the page I received. The `www.dropbox.com/developers/reference/developer-terms-and-conditions` URL returned 404. | Read; not concluded |
| Proton Drive SDK (<https://proton.me/blog/drive-sdk-january-2026>) | 2026-01-29 | Public source repo, "preview"; "not yet officially supported for use by third parties who want to integrate Proton Drive"; core file operations; no mention of quota. Relevant to the wording "Proton has no public API" (C18). | Read |

Whether Files.Read "needs README disclosure": it already has it (`README.md:145-147`), and the privacy
notice draft adds it. I recommend keeping both; Microsoft's own page confirms there is no narrower
delegated permission for `/me/drive`.

Not verified at all: Microsoft's, Google's, Proton's and Apple's trademark/brand-guideline pages; the Google
and Dropbox "revoke access" page names in the privacy draft; Entra portal wording; admin-consent rules for
work accounts; DPF certification of the three providers.

## 5. Findings (P0 to P3)
No P0 and no P1. "Who is harmed or exposed" is the owner (as publisher) or a user.

**P2-1. No published privacy notice, and the new Microsoft flow is the case Microsoft's terms point at.**
Rule: Microsoft APIs Terms s.5(d)-(e) and identity-platform terms s.2.1(7) (read 2026-11-20) ask for a
privacy statement with revoke links; Google's and Dropbox's terms ask for one too (sections 4 above).
Evidence: README has no Privacy section (`grep -n -i "privacy" README.md` finds only the macOS Full Disk
Access line 555); the draft exists in `privacy.md`. Exposure: a user cannot see what leaves the Mac or how
to revoke; the owner, if a provider ever disagrees that a personal app is outside its terms. Fix: the README
edit in section 3, after the owner's network-trace check. Whether the terms reach a user's self-registered
personal app is not decided here.

**P2-2. "Proton has no public API" (UI text and README) is a claim about a third party that its own
January 2026 SDK announcement makes doubtful.** Evidence: `cloud_quota.py:642-644`; README `:69,:465-466`;
<https://proton.me/blog/drive-sdk-january-2026> (read 2026-11-20). Rule: public claims must be supported
(`AGENTS.md`, claims list). Fix: "no quota API this app can use" (README edit 1). Exposed: Proton's reputation
and the owner's accuracy; low legal risk, but cheap to fix.

**P2-3. No non-affiliation or "use at your own risk" line in README, with four more provider names now
used.** Evidence: `name.md` addendum (grep counts); README grep above. Rule: Dropbox Developer Terms s.5.1
(do not suggest endorsement; read 2026-11-20) and Microsoft identity-platform s.2.1(5) (no Microsoft
trademarks without approval) are the two provider texts read; the others' brand pages were not read.
Descriptive plain-text use with no logos is the lower-risk form, but nothing says it is not endorsement.
Fix: README edit in section 3.

**P3-1. Google sign-in in Testing mode expires after 7 days; the README is silent.** Evidence:
`cloud_quota.py:11` (setup: "External, add yourself as test user") and Google's OAuth page (read
2026-11-20). Effect: support burden and an app that looks broken weekly for every Google account. Fix:
a README setup note (or publish the user's own project to "In production", which is the user's call and
changes what Google asks for); or accept. The owner's own Google account is affected today.

**P3-2. Entra display name.** The README tells users to name the registration "Backup Control Center"
(`README.md:132`); Microsoft's identity-platform terms s.3.1 say a display name may not be one that "is or may
be protected by trademark or other proprietary rights ... or that may cause confusion". Ties to the open name
trigger (GoodSync). Fix: say "any name you like". Not a new trigger.

**P3-3. `disconnect()` removes the local token but does not revoke at the provider**
(`cloud_quota.py:207-213`; UI button "Disconnect", `main.py:2368`). Users may think access is revoked. Privacy
draft now says so and links to Microsoft's revoke pages; an engineer could add a revoke call (Google
`oauth2.googleapis.com/revoke`, Dropbox `auth/token/revoke`: from my knowledge, not checked) or the button
could be renamed "Remove token". Owner's call.

**P3-4. Microsoft API Terms s.3(e) (no system or computer backup data in OneDrive).** Not engaged today (the
app only reads quota; the backup target is Google Drive). Noted so that "back up to OneDrive" never becomes
a feature without a re-read.

**P3-5. Microsoft API Terms s.4 (report vulnerabilities and breaches that relate to the connection to
Microsoft APIs to MSRC) and `SECURITY.md`.** Whether the clause reaches a user's own registration is
undecided; `SECURITY.md` says nothing about Microsoft. Owner may add one sentence; no trigger.

**P3-6. Sign-off record has template placeholders.** `docs/legal/signoff.jsonl` (read-only for me) line 1 has
`"by": "<name>"` and `"risk_accepted": "<why>"`. The gate accepts it, but it records no person's name or reason
for accepting the open name trigger. Owner: use real values when signing (command below).

**P3-7. DPF status of Microsoft, Google and Dropbox not verified** (`privacy.md`); keep each provider's DPA
or SCC terms on file if the owner ever becomes a controller (playbook).

**Stale-line corrections done in the pack (not findings):** `privacy.md` and `register.md` cited
`main.py:134,1142,1191,2800-2818`; now `main.py:140,1225,1322,3175-3217` (2026-11-20). `claims.md` C2 and
`privacy.md` still described `SECURITY.md:3` as wrong about the Keychain: `SECURITY.md:3` now describes the
0600 file correctly (read 2026-11-20); `privacy.md` says so.

## 6. Claims list
`docs/legal/claims.md` rows C15-C41 list every public claim the README and UI now make about the
providers, the split, Proton and links, with evidence or "unverified". Weakest: C15 (live Google/OneDrive
reads not run), C18 (Proton wording), C23 for OneDrive "(unlimited plan)", C33-C35 (Entra steps, Files.Read
content, "system-used space"), C26 (`authuser`), C31 (split not checked on a real account). Claims correctly
labelled unverified by the README already: C26, C30, C31, C32 (Google PKCE), C33 (portal steps).

## 7. Lawyer triggers
No new `- [ ] LAWYER:` line was added. The triggers listed in `AGENTS.md`/playbook are: possibly high-risk
AI, special-category or children's data, regulated finance/insurance/health/gambling, DPIA with high residual
risk, first commercial terms or client templates, a trademark conflict or filing. This change has none of the
first five (no model; no personal data of anyone but the owner; backup tool; DPIA not indicated; free). The
provider-terms questions (section 4) are not on the list and show no evidence of a contract or claim the owner
is party to: the registrations are users' own. The Entra display-name rule (P3-2) feeds the **existing** name
trigger; that line is unchanged (its text is the one recorded at the 2026-11-18 sign-off). Reconsider if the
owner publishes a shared OAuth client, a binary, a store listing, or accepts money.

## 8. Open items for the owner's sign-off (tier `public`: the sign-off is the owner's)
1. **Decide and publish (or accept) the README additions**: Privacy section, non-affiliation and "use at your
   own risk" (section 3), and the Proton wording fix; confirm the "nothing is sent to the author" claim with a
   network trace first (`privacy.md`). Until then `claims.md` C12 and the notice stay unpublished.
2. **Accept or resolve the name trigger** (GoodSync "Backup Control Center", `name.md`; plus the Entra display
   name point, P3-2): fill the owner-run register table, rename, or sign with `--accept-risk "<why>"` with a
   real reason (P3-6).
3. **Decide the three provider-term points**: (a) Google Testing-mode 7-day token expiry (note it, or move
   to production); (b) whether a Microsoft privacy statement/revoke link and an MSRC reporting line are wanted
   for a personal app (P2-1, P3-5); (c) whether `disconnect` should revoke at the provider (P3-3).

## 9. Files changed (this phase)
All under `docs/` (the pack is in the private HQ via the `docs/legal` link; nothing was committed, pushed,
built or signed by me):
- `docs/legal/privacy.md` (Microsoft rows, hosts and line numbers re-grepped, role statement, DPIA line,
  draft notice with Microsoft and revoke links, history retention 60 samples, open points)
- `docs/legal/licences.md` (addendum: dependency diff empty, stdlib-only imports, no SDK, no logos)
- `docs/legal/name.md` (addendum: provider names in use, README disclaimer check, Entra display-name rule)
- `docs/legal/notices.md` (addendum: non-affiliation wording)
- `docs/legal/claims.md` (C13 updated, C15-C41 added)
- `docs/legal/register.md` (facts, rows 13/14 updated, rows 19-20 added, no new lawyer line, release prerequisite 0,
  residual risk 0, row 15 line number)
- `docs/legal/terms.md` (Microsoft added to the non-affiliation sentence)
- `docs/audit/more-storage-providers-legal-compliance.md` (this file; in the app repo, for the owner's commit)
- Not changed: `README.md`, `SECURITY.md`, `SUPPORT.md`, `docs/legal/signoff.jsonl`, any code.

## 10. Gate status and the sign command (for the owner to run; I did not)
`python3 docs/foundry/tooling/legal_gate.py status .` (2026-11-20):
`tier: public`; `pack: 8 file(s), hash 4140596825d2 (after the last edit)`; last sign-off `<name> (owner) 2026-11-18T14:53:58 pack
7399b40d5cb4 [STALE: pack changed]`; one open lawyer trigger (the name); `legal gate: BLOCKED: legal pack
changed since the last sign-off`.

What changed since the last sign-off: this audit's pack edits (section 9), the merged feature, and
`SECURITY.md:3` now correct about tokens (fixed after the 2026-11-18 sign-off).

Residual risks: the unpublished privacy notice and disclaimers; Proton wording; Google 7-day expiry; name
unresolved; Microsoft terms applicability undecided; items "not verified" in section 4.

Command, once the owner has decided items 1-3 (the name trigger is open, so `--accept-risk` is required for an
owner sign-off; fill in your real name and reason):
```
python3 docs/foundry/tooling/legal_gate.py sign . --by "<your name>" --role owner --scope "more-storage-providers: OneDrive, Drive split, Proton tile" --accept-risk "<why the name risk is accepted>"
```

## 11. Re-check against `main` at 26b580d (review pass, 2026-11-20)
Second legal-compliance pass over the draft above (draft commit `90a216d` on `claude/adoring-goodall-5b62b5`,
carried here unchanged). Still a DRAFT, not legal advice; nothing signed, approved or "compliant". Not
re-fetched: provider pages (section 4 dates stand). Evidence: `git diff 4288539 main --stat`, greps on `main`.

**What changed since the draft's code state (4288539):** only docs, tests and one UI string
(`cloud_quota.py` +/-2 lines, `3c3a745`: Proton text "no quota API this app can use"); `4288539` is an
ancestor of `main`. Sections 1, 2 and 4 are unaffected. The draft's code citations were re-grepped on `main`:
loopback bind `cloud_quota.py:287`, scope `:487`, Graph URL `:488`, `authuser` `:666`, `disconnect` `:207`,
Proton text `:643`: all match. The Secure fixes (state/PKCE for Google and Dropbox, listener timeout, atomic
0600 credentials and 0700 folder, error text without bodies) are in `main` and the privacy-pack rows already
describe the atomic write and 0700 folder (`privacy.md:44`).

**Status of the draft's findings on `main`:**
| Finding | Status | Evidence |
|---|---|---|
| P2-1 no privacy notice | **Closed in text**, claim not measured | `README.md:780-797` (Privacy section, Google/Dropbox/Microsoft revoke links added, "not yet measured with a network trace"). The network trace is still the owner's open item. |
| P2-2 "Proton has no public API" | **Closed** | `README.md:69,468`, `cloud_quota.py:643` |
| P2-3 non-affiliation / own risk | **Closed in text** | `README.md:799-806` names Google, Dropbox, Microsoft, Proton, Apple, Qt; no logos. Company names still unchecked against a register (TODO). |
| P3-1 Google 7-day Testing expiry | **Closed in text** | `README.md:119-121` (flagged "not checked with a live account") |
| P3-2 Entra display name | **Open** | `README.md:135` still says name the registration "Backup Control Center" (feeds the open name trigger). One-line fix: "any name you like". |
| P3-3 disconnect does not revoke | **Open, disclosed** | `cloud_quota.py:207-213`; README Privacy says removal is local only |
| P3-4 Microsoft s.3(e) | Open, watch item | unchanged |
| P3-5 MSRC line in SECURITY.md | **Open** | `grep -i "microsoft\|msrc" SECURITY.md` = no hit |
| P3-6 placeholder sign-off record | **Open** (owner) | `signoff.jsonl` line 1 |
| P3-7 DPF status not verified | **Open** | unchanged |

**New points from this pass**
- N1 (P3): the pack in the HQ (`docs/legal` link) was last edited for the draft; its hash is
  `4140596825d2` and `legal_gate.py status` (run 2026-11-20 on this checkout's main repo) says BLOCKED: pack
  changed since the 2026-11-18 sign-off. Expected, not an error: a person must re-sign. I did not edit the
  pack in this pass.
- N2 (P3): `register.md:26` says "merged at `4288539`"; the merged head is now `26b580d`. Cosmetic; update when
  the owner next touches the register.
- N3: the README's "nothing else is sent" is stated as design, not measured. Keep that wording until the
  network trace is done (TODO item exists); do not strengthen it.
- N4: no `LICENSE`-side change is needed: dependency diff is empty (section 1), no logos or fonts added.
  `app-context.md` still has an unfilled placeholder (Invariants/Models used text) the session-start hook
  flags; tell the owner, not a legal item.
- Lawyer triggers: unchanged. The only open `- [ ] LAWYER:` line is the name trigger (`register.md:72`,
  GoodSync). No new one.

**Radar check (Comply scope):** not run as a command in this session (the `/radar-check` skill proposes
only and installs nothing; I did not invoke it). Nothing in this pass depends on new tools; if the owner
wants it before sign-off, run `/radar-check comply` from the main checkout.

### Sign-off list for the owner (tier `public`: owner signs; no lawyer required except the existing name trigger)
1. Run the network trace behind "no server, nothing sent" (README Privacy, TODO) and check the company names
   (Proton AG, Dropbox, Inc.) against a register.
2. Decide P3-2 (Entra display name wording), P3-3 (revoke at provider vs rename "Disconnect"), P3-5 (MSRC line).
3. Resolve or accept the name trigger (GoodSync); fill the real name and reason in the sign-off record (P3-6).
4. Sign yourself (I did not run it), after the above:
   `python3 docs/foundry/tooling/legal_gate.py sign . --by "<your name>" --role owner --scope "more-storage-providers" --accept-risk "<why the name risk is accepted>"`
