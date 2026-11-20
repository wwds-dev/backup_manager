# Secure: spec `more-storage-providers` (Foundry phase 8)

Date 2026-11-20. Read-only audit; nothing fixed. Scope: `git diff main...origin/claude/wizardly-payne-caa30e` at
`85ff446` (54c3907 plus a TODO-only commit; `cloud_quota.py` and `main.py` identical to 54c3907 for this
audit), plus the pre-existing surface it touches (`_wait_for_redirect`, `save_app_credentials`,
Google/Dropbox connect). Method: read the code, a scratch copy run on loopback only
(`scratchpad/probe.py`, no provider call, no real token), one web search. Test suite not re-run (review did: 455 pass).

## Counts
P0: 0 · P1: 0 · P2: 3 · P3: 7. No blocker for OneDrive itself; OneDrive is PKCE + state and has no secret.
The P2s are the Google/Dropbox flow now sharing a listener (pre-existing, not a regression), a stall
of that listener, and file/dir modes.

## Findings

### P2-1: Google connect has no `state` and no PKCE; code interception on the shared loopback port
- `cloud_quota.py:278-312` (`google_connect`): no `state`, no `code_challenge`; the code goes to
  `http://localhost:53789/` (`:48`) while the listener binds `127.0.0.1` only (`:265`). `localhost` may resolve to
  `::1` first; nothing listens there (probe: `bind ::1 ok: yes (no listener there)`), so another local
  user's process (or any process) can listen on `[::1]:53789`, receive the redirect with the code and
  exchange it using the client secret. The secret is a "Desktop app" secret stored 0600 but see P2-3.
  Also login-CSRF: any web page can `GET http://127.0.0.1:53789/?code=<attacker code>` in the 180 s
  window; the app exchanges it (needs a code issued to the owner's own client ID, so hard).
- Dropbox has PKCE (`:364-373`) so a stolen code is useless without the verifier; no `state`, so only the
  login-CSRF half applies. OneDrive: PKCE + `state` (`:463-471,490`); intercept useless, CSRF blocked.
- Recommendation: **fix now** in this change or the next small one, because it is cheap and the listener is now shared by
  three providers: add `state` + `compare_digest` via `_redirect_code` to Google and Dropbox, add PKCE S256 to Google
  (Google supports it for installed apps; not verified against current docs). Defer is acceptable only
  if the owner accepts a local-attacker-only risk (SECURITY.md already puts "attacker who controls your Mac" out of scope,
  but another macOS user or a browser page is not that).

### P2-2: a stalled local connection hangs the sign-in worker past its timeout
- `cloud_quota.py:242-272`: `http.server.HTTPServer` is single-threaded and the handler has no socket timeout.
  Probe: open a TCP connection to the listener and send nothing; then a real redirect GET is never answered
  (`real GET blocked: TimeoutError`) and `_wait_for_redirect(timeout=3)` had **not returned after 10.5 s**
  (`wait_for_redirect returned after stalled conn: False`); it returned only after the stalled socket closed.
  Cause: `_close_active_server` calls `server.shutdown()`, which waits for `serve_forever` to leave the stuck request.
- Result: the `ConnectWorker` QThread never ends, the Connect/Reconnect UI stays on "Opening browser…", a
  later connect cannot rebind (`_close_active_server` hangs the same way). Any local process (or page via a
  long-held fetch) can do it. Local availability only, no token exposure.
- Fix suggestion: `ThreadingHTTPServer` or `handler.timeout = 5`, and shut down without waiting.

### P2-3: `app_credentials.json` and `manual_accounts.json` are written non-atomically; directory not 0700
- `cloud_quota.py:98-101` `_write_json`: `write_text` then `chmod`; the file exists with umask mode (0644)
  until the chmod; a crash between them or a failed `chmod` leaves a world-readable file holding
  `client_secret`/`app_secret`. `mkdir` at `:99,115` uses the default mode: probe under umask 022 gave
  `sd 0o755`, `tokens.json 0o600`, `app_credentials.json 0o600` (final state fine; the window is not shown).
  A kill during `save_app_credentials` (main.py:2334) truncates the file: credentials silently lost
  (`_read_json` returns `{}`).
- `tokens.json` is correct: `mkstemp` (0600) + `fchmod` + `fsync` + `os.replace` (`:112-129`); the review's check holds.
- Fix suggestion: use `_write_json_atomic` for credentials and manual accounts, `mkdir(mode=0o700)` plus
  `chmod 0700` of the folder. P2 because the folder is 0755 and Google's client secret is what turns P2-1 from
  theory into a working attack for another local user.

### P3-1: Google and Dropbox token errors return `resp.text[:200]`
- `cloud_quota.py:305,389`. These bodies are `{"error": ..., "error_description": ...}` and do not normally echo
  the code, but they are not guaranteed to, and the text lands in `status_lbl` (`main.py:2288`) and is not logged. Recommendation: **fix now**,
  one line each, reuse `_oauth_error_text` (`:474`). Not a regression; OneDrive does it right.

### P3-2: first-GET-wins on the redirect (review P3-4) confirmed, no token theft
- `cloud_quota.py:250-260`: the first request of any kind ends the wait. For OneDrive a stray GET without a valid
  `state` yields "state check failed" (`:467`) and the real redirect is lost: login nuisance only. A
  second request before `shutdown` also overwrites `result` (`:252`, `update`), but without the 256-bit state it cannot pass the check.
  Fix: ignore requests without `code`/`error` and keep waiting.

### P3-3: `disconnect()` can block the UI thread up to ~20 s
- `cloud_quota.py:208` takes the account refresh lock; `_onedrive_access_token` holds it across the token POST
  (`:526-542`, timeout 20). Callers run on the UI thread: `main.py:1785` (`_do_reconnect`), `2398` (`do_remove`), `2419` (`do_disconnect`).
  Lock order is consistent (refresh lock → `_TOKENS_LOCK`); no deadlock found: `_store_refresh_token` only takes the RLock, `disconnect` and
  refresh never take them in the opposite order. The review's P2-1 is fixed: `_store_refresh_token` writes nothing for a removed account (`:158`).
  Fix suggestion: run disconnect in a worker or give the refresh a shorter timeout.

### P3-4: connect and an in-flight refresh can overwrite each other
- `onedrive_connect` → `_set_token_entry` (`:519`) takes no refresh lock. A refresh started before a reconnect
  stores its rotated old-grant token afterwards (`:541`), replacing the new one; if the owner reconnected as a different Microsoft
  account under the same key, the tile reads the old account. Very unlikely (needs reconnect within the ~1 s refresh).
  Fix: take `_refresh_lock` in `_set_token_entry`.

### P3-5: stored numbers are not range-checked
- Probe through `onedrive_quota` with a faked response: `used=-5` → `(-5, 10)`; `used=10**30,total="abc"` →
  `(10**30, 0)`; `used="1e3"` → ValueError; `inf` → OverflowError; `None` → TypeError. All exceptions reach the
  fetch wrapper (`main.py:1927-1930`, `except Exception`) and show as an error; no crash, no code path using the number as an index or path.
  A negative `used` renders a negative size and `pct`; clamp to ≥ 0. Total 0/invalid → "not reported" works (`:559-567`).
- Non-JSON 200 raises `ValueError` from `resp.json()` (`:516,538,557`): message is Python's, no body echoed. OK.

### P3-6: `_oauth_error_text` is safe, but `str(e)` of `requests` exceptions is shown
- `main.py:2279` (`ConnectWorker`), `main.py:1930` (`str(e)` → `quota_error`). `requests` messages contain the
  URL only; none of the new URLs carry a secret (tokens go in headers/body; `?$select=quota`). I found no log call,
  `print` or `logging` in `cloud_quota.py`. Quota history stores `used`/`total`/`drive`/`trash` only (`main.py:1311-1325`), written with
  plain `write_text` (mode 0644, non-atomic). Low sensitivity (sizes); put it in 0700 folder via P2-3.

### P3-7: public-client `client_id` is stored in plaintext and shown in the credentials form
- Expected (OneDrive client ID is not a secret; the form masks only secrets, `main.py:2299-2305`). No action except do not
  paste it in bug reports (SECURITY.md already says leave out keys).

## Checked and fine
- OneDrive: PKCE S256 with `_pkce_pair` (40 random bytes, `:351-356`); `state` = `token_urlsafe(32)`, compared with
  `compare_digest` before the code is used (`:463-471`), tests kill the mutant (review M3). No client secret.
  `redirect_uri` identical in authorize and exchange.
- Listener: `("127.0.0.1", port)` only (`:265`), static response, no reflected input, one shot, 180 s.
- Links: `web_link` uses registry literals; the only dynamic part is `authuser=` after `_EMAIL_RE.fullmatch` and
  `quote(safe='')`. Probe: `a+b%c@x.de` → `?authuser=a%2Bb%25c%40x.de`; `x@y.de&authuser=1` and `a@b.de#frag` fall back to the plain URL.
  Opened with `run_cmd(["open", url])` as an argument list (`main.py:1755-1763`), no shell, URL starts with `https://`, so no option injection.
- Network: every request uses a `https://` literal (`grep` of `cloud_quota.py`: only `http://localhost` redirect and a docstring), `timeout=20` on every call,
  no `verify=False` anywhere (`grep -n "verify" cloud_quota.py` empty).
- `requirements.txt` unchanged in the diff (`git diff main...origin/claude/wizardly-payne-caa30e -- requirements.txt | wc -l` → 0); no new import beyond stdlib (`tempfile`, `re`, `dataclasses`).
- Scope: `Files.Read offline_access` (`:459`). Microsoft's Graph reference (via search, localized pages and a mirror; see Sources)
  lists `Files.Read` as the least-privileged delegated permission for `GET /me/drive`. It still reads all of the owner's OneDrive
  files (and, for personal accounts, files shared with them); no narrower scope serves `/me/drive`. Acceptable; say so on the README setup step.
  `/common` authority also admits work/school accounts; `/consumers` would narrow it to personal accounts: owner's call.

## For Comply (flag, no legal conclusion)
- Microsoft (and Google, Dropbox) process the owner's own sign-in and quota requests; the app sends no one else's data. Add OneDrive to the
  processors/third-party services list in the privacy note, and the `Files.Read` access width. `docs/legal/` does not exist on this branch.
- Registry mentions OneDrive/Proton Drive names and logos? Names only; trademark use belongs in the name check.
- Microsoft app-registration terms for the owner's own Entra app: owner's account, not the app's.

## Not verified
- No live OneDrive/Google/Dropbox call, no real token, no Entra registration; Microsoft's loopback port-ignoring and that `Files.Read` suffices
  for `/me/drive` (search result partly from a localized page and a mirror; confirm on learn.microsoft.com/graph/api/drive-get).
- Google PKCE support for the Desktop client type; whether `localhost` resolves to `::1` first in the owner's browser (macOS usually tries both).
- Refresh-token rotation behaviour of Microsoft (single-use or not) and Dropbox/Google error-body contents.
- Behaviour of other macOS users and permissions (single-user machine assumed); the packaged `.app` (PyInstaller) was not inspected.
- Full test suite not re-run; the new tests were not read line by line.

Sources: learn.microsoft.com Graph `drive-get`, `permission-get`, `permissions overview` (search results of 2026-11-20).
