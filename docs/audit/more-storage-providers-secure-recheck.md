# Secure re-check: spec `more-storage-providers` at `b0d4d32` (Foundry phase 8, second pass)

Date 2026-11-20. Read-only. Scope: `git diff 85ff446..origin/claude/happy-kapitsa-569013` (first Secure pass was at
85ff446; report `docs/audit/more-storage-providers-secure.md`). Method: read the diff, loopback probes against a scratch copy
(`scratchpad/new/probe2.py`, no provider call, no real token), the four most relevant test files run in a scratch worktree with a
temporary `HOME` (85 tests pass; the temp HOME stayed empty, so tests do not touch live files). Full suite not re-run (child reports 514 pass).

## Counts
P0: 0 · P1: 0 · P2: 0 · P3: 3 new/residual. All three P2 and the P3s from the first pass are fixed or reduced as below.
No blocker; the three P3s are one small listener change.

## Status of the first pass
| First pass | Status | Evidence |
|---|---|---|
| P2-1 Google/Dropbox no `state`, Google no PKCE | **Fixed** | `cloud_quota.py:306-322` Google sends `state` + S256 `code_challenge`, exchange sends `code_verifier` (`:330`); Dropbox `state` (`:393-407`); both go through `_redirect_code` (compare_digest on bytes, so a non-ASCII `state` no longer raises). A stolen code on `[::1]` is now useless without the verifier. |
| P2-2 stalled connection hangs sign-in | **Fixed** | `ThreadingHTTPServer`, `daemon_threads`, `block_on_close=False`, handler `timeout=5` (`:225-235,261`). Probe A: stalled socket held open, real GET answered 200, `_wait_for_redirect` returned in 0.5 s. |
| P2-3 credentials non-atomic, dir 0755 | **Fixed** | `save_app_credentials` and `save_manual_accounts` use `_write_json_atomic` (`:108,192`; `mkstemp` 0600 + `fchmod` + `fsync` + `os.replace`); `_ensure_secrets_dir` makes the folder 0700 and tightens an old 0755 one (`:98-101`). `quota_history.json` now atomic too (`main.py:1324`). |
| P3-1 `resp.text[:200]` | **Fixed** | `:331,419` use `_oauth_error_text`; it now shows the error code only if it matches `[A-Za-z0-9_.\-]{1,64}` and tolerates non-object JSON (`:503-512`). |
| P3-2 first GET wins | **Partly fixed**, see R-1 and R-2 | stray requests (no `code`/`error`) get 404 and the listener keeps waiting (probe B: favicon 404, still waiting). |
| P3-3 `disconnect()` can block the UI up to 20 s | **Open, unchanged** | `disconnect` still takes the refresh lock held over the token POST; callers still on the UI thread (`main.py:1785,2398,2419`). Availability only. |
| P3-4 connect vs in-flight refresh | **Fixed** | `_set_token_entry` takes `_refresh_lock` then `_TOKENS_LOCK` (`:147-153`), same order as `disconnect` (`:211`) and refresh (`:557`). No path takes them the other way round: `grep` shows `_set_token_entry` is called only from the three `*_connect` functions, never under a refresh lock, and `_refresh_lock` is a non-reentrant `Lock` that is not re-taken inside `_onedrive_access_token`. No deadlock found. |
| P3-5 negative `used` | **Fixed for `used`** (`:369,471,589` `max(..., 0)`); a negative `total` from Google or Dropbox is still not clamped (R-3). |
| P3-6/P3-7 | unchanged, no action | no log or print in `cloud_quota.py`; `grep` for `verify` and `http://` finds only the redirect URI and a docstring. |

Other checks: `requirements.txt` untouched (`git diff 85ff446..origin/claude/happy-kapitsa-569013 -- requirements.txt | wc -l` → 0); no new import; every call still
`https://` with `timeout=20`; the scope and links are unchanged; `tests/conftest.py` redirects every secrets and state path to a scratch folder so no test can write live secrets.

## New and residual findings

### R-1 (P3): "first response wins" is not atomic; a second request can overwrite the real code
- `cloud_quota.py:268-283`: `first = not done.is_set()` is evaluated under `claim`, but `done.set()` runs after the 200 response is written, outside the lock.
  A second request arriving in that gap also sees `first == True` and its `update` replaces keys of the real result.
- Probe C: real `?state=REAL&code=REALCODE` and `?code=JUNK` fired together, 30 runs: **9 of 30** ended with the real `state` and the junk `code`
  (token exchange then fails "invalid_grant"). Impact is a failed sign-in, no token exposure (state is 256-bit and never leaves the app).
- Fix suggestion: set `done` (or a `claimed` flag) inside the lock, before writing the response.

### R-2 (P3): any request carrying `code` or `error` still ends the sign-in (residual login-DoS)
- Probe B: `GET /?code=x` (no state) returned 200 and ended the wait; `_redirect_code` then reports "state check failed". A local process or a web
  page (`fetch('http://127.0.0.1:53789/?code=x', {mode:'no-cors'})`) can cancel a sign-in; it cannot steal one.
- Fix suggestion (cheap, with R-1): pass the expected `state` into `_wait_for_redirect` and let the handler claim only a request whose `state` matches
  (404 otherwise), so the window stays open until the real redirect or the timeout.

### R-3 (P3): negative `total` from Google or Dropbox
- `google_quota` (`:371`) and `dropbox_quota` (`:477-480`) do not clamp `total`; a negative value is truthy in `_render_quota`, giving a negative size and percentage
  (the bar clamps). OneDrive clamps (`:593-596`). Not a security path; apply the same `max(..., 0)`.

## Not verified
- Full suite (514 tests) not re-run; only `test_oauth_hardening.py`, `test_secure_followups.py`, `test_secrets_isolation.py`, `test_onedrive.py` (85 passed).
- No live provider call: Google honouring `code_verifier` for the Desktop client type, and Google/Dropbox/Microsoft error-body contents, are from docs memory.
- Whether a browser resolves `localhost` to `::1` first (now harmless for the code, since PKCE), and the `Files.Read` scope fact from the first report (still unconfirmed on the English v1.0 page).
- Thread count under a connection flood (one daemon thread per connection, 5 s read timeout, listener lives at most 180 s): not measured; local only.
- The packaged `.app`, multi-user behaviour of the 0700 folder, and the Verify reports (read only for their claims about isolation).
