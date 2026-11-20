# Verify (re-run): spec `more-storage-providers` (Foundry phase 7)

- Commit under test: `54c3907` (scratch detached worktree `vwt2`; mutated and restored only there). Previous report was on `4965f9d`.
- Date 2026-11-20, role qa-engineer. Playbook `last-reviewed: 2026-10-14`, `status: current` (37 days, not stale).
- Test command: `QT_QPA_PLATFORM=offscreen <venv python> -m pytest -q -p no:warnings` from vwt2.

## Re-verify at 54c3907

**Overall verdict: PASS** (0 P0/P1; the three failed bullets 4b, 7, 11 now pass; the pre-existing P2-3 live-data leak is unchanged and is not caused by this spec; owner should decide to defer it).

### 1. The three failed bullets
| # | Bullet | New tests | Result at 54c3907 |
|---|---|---|---|
| 4b | disconnect during a refresh stays disconnected | `test_onedrive.py::test_store_refresh_token_never_recreates_a_removed_account`, `::test_disconnect_mid_refresh_stays_disconnected` (disconnect from a second thread mid-refresh; asserts it was blocked on the refresh lock, entry stays gone, `is_connected` False, other account kept) | pass |
| 7 | OneDrive total 0 is not "unlimited" | `::test_quota_zero_or_unusable_total_is_not_unlimited[0,"0",None,"abc",-5]`, `::test_tile_total_zero_says_not_reported` ("total not reported", no "unlimited", pct None, bar 0), `::test_tile_total_absent_still_unlimited` (guards the other branch) | pass |
| 11 | "Photos" never without "and other", label and tooltip | `test_drive_split.py::test_photos_never_alone` now loops over `lbl.text()` and `lbl.toolTip()` with `count("Photos") == count("Photos, Gmail and other")` | pass |

**Not tautological.** Production hunks reverted (`git checkout 4965f9d -- cloud_quota.py main.py`), then `tests/test_onedrive.py tests/test_drive_split.py`:
```
FAILED test_store_refresh_token_never_recreates_a_removed_account
FAILED test_disconnect_mid_refresh_stays_disconnected
FAILED test_quota_zero_or_unusable_total_is_not_unlimited[0_0]  [None]  [abc]  [-5]
FAILED test_tile_total_zero_says_not_reported
FAILED test_photos_never_alone
```
8 failures on the old code. Parameter `"0"` (string) passes on the old code too (a non-empty string was truthy there and became 0); it is a harmless duplicate, the other four params carry the proof. Restored with `git checkout 54c3907 -- cloud_quota.py main.py`; `git diff 54c3907` empty.

### 2. Full suite
- Run 1 and run 2 (JUnit XML): `tests="464" failures="0" errors="0" skipped="1"` both times (455 before + 9 new test cases: 2 + 5 params + 2 tile tests, minus none). No flakiness.
- Skipped: `tests/test_appkit_guard.py` (needs the `lab_hub` checkout, per app-context).
- Exit code: run 1 exit 0 (read via the pipe, so it is tail's, not pytest's); run 2 exit **139** (Qt teardown segfault), same as the previous report and base `d22d4c2`. Pre-existing; results are read from the JUnit XML. Intermittent in the pipe-less run, so a CI keyed on the exit code stays unreliable.
- Modes: app-context lists one (`pytest`). Branch coverage: not measured (no `coverage` module); substituted by the mutants below and reading the new branches (`total` absent / numeric / junk / negative, `account_key in tokens`, lock order).

### 2b. Live app-data folder (`~/Library/Application Support/Backup Control Center`)
`stat -f '%m %z %N'` over every file (22 files) before and after two full-suite runs: `diff` shows exactly two changed files, `quota_history.json` (mtime changed, size 14561 unchanged) and `state.json` (mtime changed, size 469 unchanged). Identical to the previous report (same two files). The installed app was running (2 processes), so as before part of this may be the app; the earlier fake-HOME and single-file isolation (state.json created from the `tests/test_resizable_columns.py` fixture; history written only by whole-suite runs; same on base `d22d4c2`) still stands. **Pre-existing leak unchanged; not made worse by this diff** (the diff touches only `cloud_quota.py`, `main.py` and two test files, all fakes with `tmp_path`).

### 3. New mutations aimed at the fixes (scratch only; `git checkout -- .` after each; `git status --short` empty and HEAD `54c3907` at the end)
Tests run: `test_onedrive`, `test_drive_split`, `test_provider_registry`, `test_tile_links`, `test_quota_fallback`, `test_overview`, `test_thread_lifetime`, `test_quota_off_ui_thread`, `test_replace_worker`.

| # | Mutation | Result | Killed by |
|---|---|---|---|
| N1 | `disconnect` without the refresh lock (`with _TOKENS_LOCK:` only) | Killed | `test_disconnect_mid_refresh_stays_disconnected` |
| N2 | tile treats `total == 0` as unlimited again (`elif not total:`) | Killed | `test_tile_total_zero_says_not_reported` |
| N3 | tooltip reverted to the old "Photos from Gmail" text | Killed | `test_photos_never_alone` |
| N4 | `_store_refresh_token` recreates a removed account | Killed | `test_store_refresh_token_never_recreates_a_removed_account` |
| N5 | `onedrive_quota`: total 0 becomes None (`int(...) or None`) | Killed | `test_quota_zero_or_unusable_total_is_not_unlimited[0_0,0_1,-5]` |
| N6 | junk/null total becomes None | Killed | `...[None]`, `...[abc]` |
| N7 | negative total kept | Killed | `...[-5]` |
| M11 (earlier survivor) | tile hides the split when `drive == 0` (`if not drive_files`) | **Survived** | none: tile-level `drive == 0` is still untested |
| M13 (earlier survivor) | OneDrive mount prefix `"OneDrive-"` instead of `"OneDrive"` | **Survived** | none: no test with a bare `OneDrive` folder name |

7 of 7 new mutants killed; the two earlier survivors are unchanged (P3, safe degrade / near-equivalent), not addressed by the fix commits, which the owner did not ask for.
Side note: during the N5 to N7 runs an untracked file named `None` (16 bytes) appeared in the vwt2 root; it was not there on a clean run of `test_onedrive.py` at 54c3907. It looks like a test writing to a path built from a `None` under a broken `total`; not investigated further, removed (scratch only). Worth a look by Build if it recurs on the real code (not seen at 54c3907).

### 4. Other bullets unaffected
`git diff 4965f9d 54c3907` touches `cloud_quota.py` (`_store_refresh_token`, `disconnect`, `onedrive_quota`), `main.py` (the split tooltip and the no-percentage branch of `_render_quota`) and tests only. Full suite 464 passed, 0 failed, so all earlier passing tests pass (bullets 1-3, 4, 5, 6, 8-10, 12-17). One thing changed by the diff that earlier tests did not cover: `elif total is None` / `else` in the tile now applies to any provider returning `total == 0` (Google/Dropbox); covered by the tile tests only for OneDrive's `Quota`, which is provider-independent. Disconnect now takes a lock that a refresh holds during a network call: a disconnect click blocks until that call returns (the Build log notes the request has a timeout; the blocking-on-the-UI-thread effect is not measured, see not verified).

## Updated per-bullet verdicts
| # | Bullet | Verdict now |
|---|---|---|
| 1 | OneDrive in Add Account | pass (weak assertion, P3-3) |
| 2 | OneDrive tile "X used of Y" | pass |
| 3 | Mounted OneDrive-* Connect link | pass (bare name untested, M13) |
| 4 | Refresh stores rotated token | pass |
| 4b | Disconnect during refresh | **pass** (was fail) |
| 5 | 400/401 reconnect | pass |
| 6 | Failed call shows last-known | pass |
| 7 | Total 0 not "unlimited" | **pass** (was fail) |
| 8-10, 12 | Google split, hidden cases, trash, last-known split | pass |
| 11 | "Photos" only with "and other" (label and tooltip) | **pass** (was fail) |
| 13-15 | Proton, links, off UI thread | pass |
| 16 | Full suite green | pass (464/0/0, 1 skipped) |
| 17 | New logic mutation-checked | pass (7/7 new killed; 2 earlier survivors open, P3) |

## Open findings, ranked
| P | Finding | Status |
|---|---|---|
| P2-3 | Full suite writes the owner's live `state.json` and (with tokens) `quota_history.json`; pre-existing since `d22d4c2` | open, unchanged; owner to defer or schedule |
| P3-1 | Disconnect can block on an in-flight refresh (UI thread wait) | new, not measured |
| P3-2 | Tile `drive == 0` untested (M11) | open |
| P3-3 | No direct "OneDrive in Add Account" assertion; bare "OneDrive" prefix untested (M13) | open |
| P3-4 | Exit 139 at Qt teardown (intermittent in this run), CI keyed on exit code cannot be relied on | open, pre-existing |
| P3-5 | Reviewer's P3s left on purpose (stale copy, double history read, redirect GET, Google/Dropbox `state`) | deferred per fix log |

## Not verified
- Branch coverage of changed lines (no `coverage` module).
- Live calls (OneDrive sign-in, real Google `storageQuota`, Dropbox).
- Visual layout / screenshots; the "total not reported" wording on screen.
- Whether a disconnect click visibly freezes the UI while a refresh is in flight.
- Which test leaks to the live folder; whether the suite makes live API calls.
- Secure-phase items, spec "memory" facts, Python-version compatibility of `str | None` in the PyInstaller build.

---
# History: verify at 4965f9d (previous report, verdict FAIL)
Kept as in `verify.md`: 14 mutants M1-M14 (12 killed; M11, M13 survived), findings P2-1 (disconnect race), P2-2 (total 0 shown as unlimited), P2-3 (live-folder leak), P3-1 (tooltip "Photos"), P3-2 to P3-5; suite 455/0/0, 1 skipped, exit 139. Full text: `/private/tmp/claude-501/-Users-as-Documents-lab-active-backup-manager--claude-worktrees-gifted-yonath-b68e3c/480b605c-79de-4832-9afa-ba934286025a/scratchpad/verify.md`.


---

## Second pass at 2084ec2 (2026-11-20)

Scope: the four Secure fixes (P2-1, P2-2, P2-3, P3-1) on `claude/wizardly-payne-caa30e` at `2084ec2`, checked in a detached scratch checkout; production code untouched. **Verdict per fix: P2-1 PASS, P2-2 PASS (two missing tests G1, G2), P2-3 PASS, P3-1 PASS. Suite 503/0/0, 1 skipped, twice.** Mutation figures: 31 planted, 24 killed, 7 survived (3 equivalent, 2 real test gaps, 1 killed by another file, 1 equivalent error-path). Detail follows.


Playbook `docs/playbooks/qa-engineer.md`: last-reviewed 2026-10-14, status current (37 days old, not stale).
App has no model calls (`## Models used`: None), so check 5 (live eval) does not apply.
All work in the scratch checkout TIP (`.../scratchpad/tip`); `git -C TIP status --short` is empty after every mutation (restored with `git checkout -- cloud_quota.py`; checked after the batch and again after the suite runs).

### Verdict
**PASS with findings.** All four fixes are closed in code and covered by tests, and the suite is green and stable.
Two production-behaviour mutants survive the new tests (listener bind address, handler timeout): missing tests, no production bug. Ranked gaps at the end.

### 1. Mutation check (tests/test_oauth_hardening.py; survivors re-run against all of tests/ except test_main_window.py)
Scripts: `scratchpad/mut.py`, `mut2.py`; raw output `mut_out.txt`, `mut2_out.txt`. 31 mutants planted, 24 killed, 7 survived (3 equivalent or near-equivalent, 3 real test gaps, 1 killed only by another file).

| Fix | Mutant | Result | Failing test (first) |
|---|---|---|---|
| P2-1 | a. skip state compare, Google | KILLED | test_connect_rejects_bad_or_missing_state[False-google] (+2) |
| P2-1 | b. skip state compare, Dropbox | KILLED | test_connect_rejects_bad_or_missing_state[False-dropbox] (+2) |
| P2-1 | b2. skip state compare, OneDrive (extra) | KILLED only by tests/test_onedrive.py::test_connect_rejects_bad_or_missing_state (survives hardening file alone, which does not cover OneDrive; fine) | |
| P2-1 | c1. drop code_verifier from Google token POST | KILLED | test_connect_uses_pkce_s256_and_sends_the_verifier[google] |
| P2-1 | c2. drop code_challenge from Google auth URL | KILLED | same |
| P2-1 | c3. Google method S256 -> plain | KILLED | same |
| P2-1 | c4. Google sends a fixed verifier not matching challenge | KILLED | same |
| P2-1 | d1. accept missing/empty state (`if got and not compare`) | KILLED | test_connect_rejects_bad_or_missing_state[-google], [False-*] (4 fail) |
| P2-1 | d2. error path: state ignored when `error` is in the result | SURVIVED (equivalent: either way no code, no exchange; only the message text differs) | none |
| P2-1 | e. state constant per attempt | KILLED | test_state_differs_per_attempt |
| P2-2 | a. remove handler timeout (`timeout = None`) | **SURVIVED** (also against all tests/) | none |
| P2-2 | a3. handler timeout 5 -> 600 s | **SURVIVED** | none |
| P2-2 | a2. back to single-threaded HTTPServer | KILLED | test_stalled_connection_does_not_block_the_real_redirect, ..._past_its_timeout, test_first_sign_in_response_wins... |
| P2-2 | b. stray request (no code/error) ends the wait | KILLED | test_request_without_code_or_error_is_ignored[/favicon.ico], [/], [/?foo=bar] |
| P2-2 | c. `error=` redirect ignored | KILLED | test_error_redirect_ends_the_wait |
| P2-2 | d. last response wins (no first-claim) | KILLED | test_first_sign_in_response_wins_over_a_later_one |
| P2-2 | e. bind 0.0.0.0 instead of 127.0.0.1 | **SURVIVED** (also against all tests/) | none |
| P2-2 | f. daemon_threads False + block_on_close True | KILLED | test_stalled_connection_does_not_hold_the_wait_past_its_timeout |
| P2-3 | a1. mkdir 0755 and no chmod | KILLED | test_new_folder_is_0700_and_file_0600[*], test_existing_loose_folder... (6 fail) |
| P2-3 | a2. temp file 0644 at create (fchmod 0644) | KILLED | test_file_is_0600_before_it_takes_the_real_name[*] (9 fail) |
| P2-3 | a3. drop fchmod | SURVIVED (equivalent: `mkstemp` already creates 0600; fchmod is belt and braces) | none |
| P2-3 | b1. drop folder chmod (keep mkdir mode) | KILLED | test_existing_loose_folder_and_file_are_tightened[*] |
| P2-3 | b2. drop `mkdir(mode=0o700)` (keep chmod) | SURVIVED (near-equivalent: end state identical; only a microsecond window with umask-022 0755 folder, files inside are 0600 regardless) | none |
| P2-3 | c. non-atomic write (replace -> copy over path) | KILLED | test_failed_replace_leaves_the_old_file[*], test_file_is_0600_before_it_takes_the_real_name[*] |
| P2-3 | c2. no temp cleanup on failure | KILLED | test_failed_replace_leaves_the_old_file[*] |
| P2-3 | d. credentials via plain write_text | KILLED | ..._credentials |
| P2-3 | e. manual accounts via plain write_text | KILLED | ..._manual |
| P3-1 | a. Google echoes `resp.text[:200]` | KILLED | test_token_exchange_error_with_a_non_json_body[google], ..._shows_the_error_code_only[google] |
| P3-1 | b. Dropbox echoes `resp.text[:200]` | KILLED | same, [dropbox] |
| P3-1 | c. drop the error-code regex | KILLED | test_error_text_ignores_odd_error_fields[body1], [body2] |
| P3-1 | d. AttributeError not caught | KILLED | test_error_text_ignores_odd_error_fields[body0] |

PASS/FAIL per fix:

| Fix | Closed in code | Tested | Verdict |
|---|---|---|---|
| P2-1 state + Google PKCE | yes (cloud_quota.py:304-305, 313-316, 318, 328; 388-389, 400, 403; 490-498) | yes, all mutants killed except an equivalent one | PASS |
| P2-2 listener DoS | yes (cloud_quota.py:223-231 ThreadingHTTPServer, daemon_threads, block_on_close False; 258-263 timeout; 264-272 stray 404; 299 loopback) | threading, stray, error, first-wins killed; **timeout value and loopback bind not tested** | PASS with test gaps (G1, G2) |
| P2-3 secrets files | yes (cloud_quota.py:98-101, 113-133, 190) | yes | PASS |
| P3-1 error text | yes (cloud_quota.py:331, 416, 500-510) | yes, both providers separately | PASS |

### 2. Suite regression at TIP
Command: `cd TIP && QT_QPA_PLATFORM=offscreen PY -m pytest -q -p no:warnings --junitxml=<scratch>/junitN.xml`
- Run 1: exit 139 (Qt teardown crash, pre-existing), JUnit `tests=503 failures=0 errors=0 skipped=1`, 47.7 s.
- Run 2: exit 134 (also Qt teardown abort), JUnit `tests=503 failures=0 errors=0 skipped=1`, 42.7 s. Counts identical, no flakiness.
- First pass was 456 tests (455 pass + 1 skipped); the verify report at gifted-yonath records 464 after its fixes. 503 - 464 = 39 = the new `test_oauth_hardening.py` (collected 39). `git diff 85ff446 2084ec2 --stat -- tests` shows only that file; so no earlier test was removed or edited. 502 pass, 1 skipped.
- `tests/test_oauth_hardening.py` alone, twice: 39 passed both times. With test_onedrive.py and test_provider_registry.py: 54 passed (JUnit `junit_cq.xml`).
- Not run: pytest-randomly / --timeout (not installed or configured in the venv; not verified). Not run: `-W error::pytest.PytestDeprecationWarning`.
- Branch coverage of changed lines: `coverage` is not installed in the venv (`No module named coverage`), so a coverage number is not verified. Substitute: the 31 mutants above exercise every changed branch in `_redirect_code`, `_wait_for_redirect.do_GET`, `_write_json_atomic`, `_ensure_secrets_dir`, `_oauth_error_text`; the only unexercised line-level behaviour is the handler timeout value and the bind host (G1, G2).

### 3. New listener tests and live folder
- tests/test_oauth_hardening.py uses only `127.0.0.1` sockets (`_free_port`, `socket.create_connection(("127.0.0.1", port))`, lines ~134-160). An autouse fixture (lines 22-33) replaces `requests.get`, `requests.post` and `webbrowser.open` with a function that raises `AssertionError("unexpected network call")`; `_connect` swaps in fakes for them. No `urlopen`, no provider hostname call. The only provider-name strings are the URL constants that `webbrowser.open` receives into a fake. PASS.
- Fixture `isolated` patches `SECRETS_DIR`, `CREDENTIALS_FILE`, `TOKENS_FILE`, `MANUAL_ACCOUNTS_FILE` to tmp_path; `fresh_dir` does the same for a not-yet-created `sd`. No test targets the live folder. PASS.
- Other test files patch only `SECRETS_DIR` and not the `*_FILE` constants (test_overdue_cooldown.py:23, test_drive_split.py:109, test_quota_fallback.py:36, test_quota_off_ui_thread.py:36, test_resizable_columns.py:31, test_tile_windows.py:46, test_main_window.py:37/294). Those that never call `save_*` are harmless. Not verified per test; the live diff below shows no secrets file was touched. See P3 note S6.
- Live folder `~/Library/Application Support/Backup Control Center`, mtimes before (saved `mtimes_before.txt`) vs after (`mtimes_after.txt`) the two full runs and the other runs: changed = `quota_history.json`, `state.json` (pre-existing leak from first pass or the running installed app) and `icloud_du.log`. `icloud_du.log` content is `... not_downloaded=2 other_errors=0 ...`; the string `not_downloaded` is not in TIP's main.py (grep count 0), so it was written by the installed app (pid 31299, `/Applications/Backup Control Center.app`, running), not by a test. Same for the other two (written by the running app on its own timer); not attributable to tests with certainty, but no new test in this pass touches them.
- Unchanged: `app_credentials.json` (1782574518), `tokens.json` (1785002817), all other files and the folder.
- Permission bits before vs after: folder `drwxr-xr-x` both; `diff perms_before.txt <(after)` empty; secrets files remain `-rw-------`. No `.app_credentials.json.*.tmp` or similar temp file left in the live folder. No new finding on this check.
- Note: the live folder is still 0755 (the installed build predates this code). It is tightened to 0700 on the first secrets write by the new build (see S5).

### 4. Security spot-check (read-only, TIP)
Closed against the secure report wording:
- **P2-1 closed.** `state = secrets.token_urlsafe(32)` per attempt (google :305, dropbox :389, onedrive :519); `_redirect_code` (:490-498) requires non-empty `state` and `secrets.compare_digest(got, expected_state)` BEFORE reading the code; missing, empty and wrong all rejected with no token POST (tests). Google PKCE: `_pkce_pair()` per attempt (:304), verifier from `secrets.token_bytes(40)` (:379), challenge S256, `code_verifier` sent only in the token POST (:328). The verifier is a local variable: not stored, not reused across attempts, not logged (no logging in module; `Handler.log_message` is a no-op, :281).
- **P2-2 closed.** Server is `ThreadingHTTPServer` with `daemon_threads=True`, `block_on_close=False` (:223-228); `Handler.timeout = 5` (:259, applied by `StreamRequestHandler.setup`); bound to `("127.0.0.1", port)` (:287); stray requests without `code`/`error` get 404 and do not end the wait (:262-266); first response wins under a lock (:267-271); `_close_active_server()` shuts down on completion and before the next start; overall wait bounded by `done.wait(180)`. Verified by tests: port rebinds after a stalled wait.
- **P2-3 closed.** Folder `mkdir(mode=0o700)` then `chmod 0700` (:98-101); every secrets write (credentials :109, tokens :144, manual :190) goes through `_write_json_atomic` (:113-133): `mkstemp` in the same dir (random name, `O_EXCL`, no symlink follow, 0600 from creation), explicit `fchmod 0600`, `fsync`, `os.replace` (same directory, so same filesystem, atomic), temp removed on any `BaseException`. `os.replace` onto a symlinked target replaces the link, not its target.
- **P3-1 closed.** Both providers (:331, :416) and OneDrive (:545) use `_oauth_error_text` (:500-510): status plus an error code only if it matches `[A-Za-z0-9_.\-]{1,64}`. No `resp.text` anywhere in the module (grep). `raise_for_status()` callers (refresh and quota paths) surface requests' message, which carries status and URL but no body; tokens travel in POST bodies or Bearer headers, not URLs (not verified for every call site).

New observations (none blocks):
| ID | Sev | file:line | Finding |
|---|---|---|---|
| S1 | P3 | cloud_quota.py:493 | `secrets.compare_digest(str, str)` raises `TypeError` when the redirect's `state` has non-ASCII characters (reproduced with `?code=x&state=%C3%A9`: `TypeError comparing strings with non-ASCII characters is not supported`). Fails closed (no exchange); `ConnectWorker.run` (main.py:2272-2276) catches `Exception` and shows the odd message. Fix: compare `.encode()` bytes, or catch TypeError. No test covers it. |
| S2 | P3 | cloud_quota.py:262-272 | Any local process or web page hitting `http://127.0.0.1:<port>/?code=junk` first ends the wait; the user then sees "state check failed. Try again." That is a sign-in DoS only; state blocks code injection. Inherent to a loopback redirect; the stray-request 404 narrows it to requests carrying `code` or `error`. Note only. |
| S3 | P3 | cloud_quota.py:490-498 | An `error=access_denied` redirect that carries no or a wrong state shows the "state check failed" message instead of "denied". Cosmetic; mutant P2-1d2 is equivalent for security. |
| S4 | P3 | cloud_quota.py:118-129 | SIGKILL or power loss between `mkstemp` and `replace` leaves `.<name>.XXXX.tmp` (0600, in the 0700 folder; possibly partial secret). Normal exceptions and Ctrl-C are cleaned up. No parent-directory fsync (durability only). |
| S5 | P3 | cloud_quota.py:98-101 | The folder is tightened only on a write, never on read; the live folder stays 0755 (verified above) until the first save by the new build. Its secrets files are already 0600, so exposure is the other 0644 files in it (quota_history.json, state.json, env_records). `os.chmod` follows a symlinked SECRETS_DIR (owner's own path; negligible). |
| S6 | P3 | tests (7 files listed in section 3) | Those files patch `SECRETS_DIR` but not `TOKENS_FILE` and friends. The new `_write_json_atomic` derives the temp dir from `path.parent`, so a test that calls a save function while patching only `SECRETS_DIR` would write a temp file and `os.replace` over the LIVE file, while chmod'ing the patched dir. Not observed to happen (live files unchanged after the full suite); the risk is latent. Suggest a conftest autouse fixture that patches all four constants. |

### Ranked gaps
1. **G1 (P2, missing test)**: nothing asserts the listener binds loopback only. Mutant `("0.0.0.0", port)` survives the whole suite. Guards a security property. Test idea: while a wait is active, `cloud_quota._active_server.server_address[0] == "127.0.0.1"`.
2. **G2 (P2, missing test)**: nothing asserts the per-connection handler timeout. Mutants `timeout=None` and `600 s` survive. Without it a stalled connection's daemon thread and socket persist until the client closes. A test can monkeypatch `_REDIRECT_REQUEST_TIMEOUT = 0.3` (read when the handler class is built inside `_wait_for_redirect`), open a silent connection, keep the wait alive with a stray request, and assert `recv` returns `b""` within about 2 s. Production code is correct today.
3. **S1 (P3)**: non-ASCII `state` raises TypeError instead of a clean rejection.
4. **S6 (P3)**: tests that patch only `SECRETS_DIR` could write the live secrets files via the new `path.parent` temp dir; add a shared fixture.
5. **P3 near-equivalent survivors**: P2-3b2 (mkdir mode), P2-3a3 (fchmod), P2-1d2; no action needed, recorded for transparency.
6. S2-S5 as noted.

### Not verified
- Branch coverage number (coverage.py not installed); substituted by the mutation analysis above.
- pytest-randomly, per-test timeout, `-W error::PytestDeprecationWarning` runs.
- test_main_window.py was excluded from the survivor re-runs (the 6 survivors were re-run against the rest of tests/ only); it was in both full runs.
- Whether the three changed live files were written by the installed app or by a test cannot be proven separately; icloud_du.log is shown to be the app's (format). No live provider call, no real token used; no build, install or merge.
- Windows/Linux behaviour of `os.fchmod`/umask (macOS only).
- Every `raise_for_status` call site's URL contents.


---

## Third pass at f050c9d (2026-11-20)

Scope: the follow-up that closes the second pass test gaps (G1 loopback bind, G2 handler timeout) and P3s S1 (non-ASCII state) and S6 (conftest isolation). **G1 PASS, G2 PASS (R1 residual), S1 PASS, S6 PASS (R2 residual), suite 507/0/0 1 skipped twice, live secrets files unchanged.**


Playbook `docs/playbooks/qa-engineer.md`: last-reviewed 2026-10-14, status current (37 days; not stale). App calls no model (app-context `## Models used`: None), so the live-eval item does not apply.

### Verdict: PASS for G1, G2 (with one residual), S1, S6 (with one residual), suite, live folder

| Item | Result | Evidence |
|---|---|---|
| G1 listener binds 127.0.0.1 | PASS | `0.0.0.0` and `""` mutants KILLED by `test_listener_binds_loopback_only` (tests/test_oauth_hardening.py:356; source cloud_quota.py:286) |
| G2 handler timeout | PASS, residual R1 | `None` KILLED, constant ignored (literal 5) KILLED, both by `test_silent_connection_is_closed_after_the_handler_timeout` (:368). `600` SURVIVED (see R1). Test: 10 runs, all pass, call time 0.83-0.92 s each, recv bounded by `settimeout(2)`; also passed in both full-suite runs. Not flaky, waits well under 2 s |
| S1 non-ASCII state | PASS | Revert (compare str) KILLED by `test_non_ascii_state_is_rejected_cleanly[google]` and `[dropbox]`. Fix at cloud_quota.py:493 |
| S6 conftest isolation | PASS, residual R2 | tests/conftest.py:9-15 autouse fixture patches SECRETS_DIR, CREDENTIALS_FILE, TOKENS_FILE, MANUAL_ACCOUNTS_FILE to tmp_path; later own-patching tests still win (monkeypatch order); full suite green with 5 test files that patch these themselves. Scratch test calling the real `save_app_credentials`, `save_tokens`, `save_manual_accounts`, `add_manual_account` with no patching: passed, files landed in tmp (0600), live-folder snapshot identical, no scratch marker in live JSON |
| Full suite x2 | PASS | JUnit j3_1.xml and j3_2.xml: tests 507, failures 0, errors 0, skipped 1, both runs (exit 139 is the known Qt teardown). `git diff 2084ec2 HEAD -- tests` has no removed or changed lines, only additions |
| Live folder | PASS | tokens.json (1785002817) and app_credentials.json (1782574518) mtimes unchanged; permissions diff empty. Five other files changed, see below |

### Mutants (cloud_quota.py, each reverted by `git checkout -- cloud_quota.py`; `git status` clean at the end)
Script `scratchpad/mut3.py`, output `scratchpad/mut3_out.txt`. Command: `QT_QPA_PLATFORM=offscreen PY -m pytest -q -p no:warnings tests/test_oauth_hardening.py`.

| Mutant | Result | Failing tests |
|---|---|---|
| G1a bind 0.0.0.0 | KILLED | test_listener_binds_loopback_only |
| G1b bind "" | KILLED | test_listener_binds_loopback_only |
| G2a handler timeout None | KILLED | test_silent_connection_is_closed_after_the_handler_timeout |
| G2b `_REDIRECT_REQUEST_TIMEOUT = 600` | SURVIVED | none (R1) |
| G2c constant ignored, literal 5 | KILLED | test_silent_connection_is_closed_after_the_handler_timeout |
| S1 revert, compare str not bytes | KILLED | test_non_ascii_state_is_rejected_cleanly[google], [dropbox] |
| Regression: skip state compare Google | KILLED | test_connect_rejects_bad_or_missing_state[wrong-state-google], [-google], [False-google], plus non_ascii[google] (4) |
| Regression: no folder chmod | KILLED | test_existing_loose_folder_and_file_are_tightened[credentials], [manual], [tokens] |
| Regression: non-atomic write | KILLED | test_failed_replace_leaves_the_old_file[tokens], test_file_is_0600_before_it_takes_the_real_name[x3] (6 total) |
| Regression: drop fchmod | SURVIVED, equivalent | mkstemp already creates 0600 (same as second pass P2-3a3) |

### Residuals (ranked)
1. R1, P3 (test gap): the G2 test sets the constant to 0.3 with monkeypatch, so a production value of 600 is overwritten and cannot be detected. Mutant `None` and a hard-coded literal are caught, a huge constant is not. Cheap fix: assert `cloud_quota._REDIRECT_REQUEST_TIMEOUT <= 10` in the test. The docstring comment at :369 claims it kills 600; that claim is wrong.
2. R2, P3 (S6 scope): conftest isolates only the four cloud_quota paths. main.py derives `_STATE_FILE` (main.py:1200), `_QUOTA_HISTORY_FILE` (:1297), `_INSTANCE_LOCK_FILE` (:6036) and the icloud_du.log path (:924) from SECRETS_DIR at import time, so the fixture does not redirect them. Tests that touch them patch them individually (test_overdue_cooldown, test_resizable_columns, test_onedrive, test_drive_split, test_quota_*, test_tile_links), and I found no sign of test data in the live files, but nothing enforces it for a future test. These are not secrets files.

### Live folder diff (`~/Library/Application Support/Backup Control Center`)
Changed mtimes: gui.lock, env_last_use.json, state.json, icloud_du.log, quota_history.json. Cause: the installed app `/Applications/Backup Control Center.app` is running (pid 39711, started 19:35) and these are its own files (lock, history sampler, scan log, state). Evidence: quota_history last samples are 19:35 for the three real accounts, state.json has no test markers (webhook_url empty, log_scroll_pos 0, no "not a date"), no test account keys. I cannot rule out with certainty that a test run touched one of them while the app ran, but the content shows no test data. Nothing in the live folder was modified by me. Baselines: mtimes_before2.txt / mtimes_after2.txt, perms_before2.txt / perms_after2.txt.

### S1 spot check
Scratch tests (deleted, not committed), `_redirect_code` direct plus full `connect()` with fake browser/redirect/token endpoint: state values `é`, `☃☃`, empty, missing, 43 x "x" (equal length, wrong), 44 x "x", 43 emoji, all for google and dropbox: each returns `(False, "Sign-in response did not match this request (state check failed). Try again.")`, no exception, `requests.post` never called. Direct: correct state returns the code. Same message for all cases.

### Not verified
- OneDrive through `connect()` with a bad state: my scratch harness lacked a OneDrive client id (returned "No OneDrive Client ID saved yet."), so only the shared `_redirect_code` (cloud_quota.py:490, used at :318, :403, :531) was checked for it.
- Branch coverage of the changed lines was not re-run this pass (the change is one expression plus a fixture; both branches of the line are hit by the tests above).
- No live provider calls, no real tokens (none used).

## Third pass at f050c9d (2026-11-20, qa-engineer)
Scope: the Build follow-up b3e43e6 + d28c9b7 against gaps G1, G2, S1, S6 from the second pass. Work was done in a
detached scratch worktree of f050c9d (removed afterwards); the real worktree was not edited except this file.
Loopback sockets only; no provider call. Playbook `docs/playbooks/qa-engineer.md`: status current, last-reviewed 2026-10-14 (37 days, not stale).

### Verdict
| Gap | Verdict | Evidence |
|---|---|---|
| G1 loopback bind | CLOSED | mutant `("0.0.0.0", port)` fails `test_listener_binds_loopback_only` (only failure) |
| G2 handler timeout | CLOSED, one residual (below) | mutants `timeout = None` and literal `timeout = 600` fail `test_silent_connection_is_closed_after_the_handler_timeout` |
| S1 non-ASCII state | CLOSED | mutant `compare_digest(got, expected_state)` (str) fails both `test_non_ascii_state_is_rejected_cleanly[google|dropbox]` |
| S6 secrets isolation | CLOSED as written, but not demonstrably load-bearing (below) | conftest autouse fixture; live files unchanged after two full runs |

### Mutation table (cloud_quota.py, each restored with `git checkout`; scratch `git status` clean after)
Commands: `.venv/bin/python -m pytest -q -p no:warnings tests/test_oauth_hardening.py --junitxml=...` and the same on
`--ignore=tests/test_main_window.py tests`. Counts from the JUnit XML (`QT_QPA_PLATFORM=offscreen`).
| # | Mutant | test_oauth_hardening.py (43 tests) | tests/ minus test_main_window (473) | Result |
|---|---|---|---|---|
| M1 | bind `("0.0.0.0", port)` | 1 failure: `test_listener_binds_loopback_only` | 1 failure, same test (exit 139 Qt teardown) | KILLED |
| M2 | Handler `timeout = None` | 1 failure: `test_silent_connection_is_closed_after_the_handler_timeout` | 1 failure, same test (exit 134) | KILLED |
| M3a | Handler literal `timeout = 600` | 1 failure, same test | not run | KILLED |
| M3b | module constant `_REDIRECT_REQUEST_TIMEOUT = 600` | 0 failures (exit 0) | 0 failures | SURVIVED |
| M4 | S1 revert: `compare_digest(got, expected_state)` | 2 failures (google, dropbox non-ASCII) | 2 failures, same tests | KILLED |

M3b survives because the test itself patches the constant to 0.3, so the shipped default (5 s) is not pinned. The
fix log's "timeout 600" mutant is killed only in the literal form M3a. Low risk (a 600 s default would still be a
daemon thread, closed on server shutdown), but a one-line assertion `cloud_quota._REDIRECT_REQUEST_TIMEOUT <= 30` would close it. Gap rank: P3.

### Test quality
- Flakiness: `test_oauth_hardening.py` run 5 times, 43 passed each time (5/5 green). The timeout test uses a 0.3 s
  patched timeout and a 2 s recv guard, so it is timing-dependent but with a 6x margin; no network beyond 127.0.0.1;
  ports from `_free_port()`. Not stress-tested under load (not verified).
- `test_listener_binds_loopback_only` asserts `server_address[0] == "127.0.0.1"` on the live server: can fail (M1), no over-mocking. It reads
  a private global `_active_server`; coupling is acceptable.
- `test_silent_connection...` sends a stray 404 request while a silent connection is held, so it also shows the
  wait survives stray requests; assertion `recv(1) == b""` can fail (M2, M3a). Teardown completes the wait and joins.
- `test_non_ascii_state...` asserts message, no token POST, and the direct `_redirect_code` return; can fail (M4).
- conftest: the autouse fixture repoints the four secrets paths to `tmp_path/_secrets`. Per-test patches still work:
  full suite is 507/0 failures, including tests that patch the same names. Live files: before/after a full run
  (twice) `app_credentials.json` (mtime 1782574518, 263 bytes, sha1 3fccc7bc...) and `tokens.json` (mtime 1785002817, 540 bytes) are
  identical (`diff` of stat output: SECRETS_UNCHANGED); `manual_accounts.json` does not exist, still absent.
  Negative control: with `HOME` pointed at an empty scratch dir and conftest removed, a full run created no secrets file there
  (only `state.json`); so no current test writes the secrets files even without conftest. The fixture is a sound
  guard against future tests, but this pass cannot show it catching anything today (P3, informational).
- Observation: `state.json` (in the same Application Support dir) is written during the full run with real `HOME`
  semantics, outside conftest's scope. Not a secret, but not isolated either; I did not check whether it is the live file's mtime
  that moves, because the running app also rewrites it (not verified). P3.

### Full suite (every mode: app-context lists one mode, `.venv/bin/python -m pytest`)
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -p no:warnings --junitxml=...`, scratch tree at f050c9d:
| Run | tests | failures | errors | skipped | exit |
|---|---|---|---|---|---|
| 1 | 507 | 0 | 0 | 1 | 139 (known Qt teardown crash) |
| 2 | 507 | 0 | 0 | 1 | 139 |
Two further runs with a scratch `HOME` (with and without conftest) also ended 139; counts not read from XML (not verified).
Coverage of changed lines: not measured (no coverage tool configured); the mutation kills above are the evidence.

### Ranked gaps
1. P3: default handler timeout value unpinned (M3b survives).
2. P3: conftest guard shown correct but not shown necessary; `state.json` not isolated.
3. Process: this file lives on branch `claude/charming-pare-c71b74`; it was copied into this worktree to append this section.

Overall: PASS for G1, G2, S1, S6; no P0/P1/P2 open.

## Fourth pass at e6ef87c (Verify, QA engineer)

Playbook `docs/playbooks/qa-engineer.md`: `status: current`, `last-reviewed: 2026-10-14` (37 days old, not stale).
Method: detached scratch copy (`git archive HEAD`) of the tree; every run used a fresh scratch `HOME` containing
`Library/Application Support/Backup Control Center` (the "scratch live folder"), except the one real-HOME run at the end.
Worktree untouched except this file (`git status --short` showed only this file modified). Mutations restored in the scratch copy
(`diff -r` of tests/ and cloud_quota.py against the worktree: RESTORED).

### Verdicts
- **R1 (production handler timeout unpinned): CLOSED.** `test_production_handler_timeout_is_short` asserts
  `0 < cloud_quota._REDIRECT_REQUEST_TIMEOUT <= 10` and fails for both 600 and 0 (table).
- **R2 (tests wrote main.py import-time paths): CLOSED.** The session baseline is what actually keeps files out of the
  live folder; `test_secrets_isolation` is what guards the per-test layer and the main.* patches (table).

### Mutation table (scratch copy, `HOME` = scratch)
| # | Mutation | Result |
|---|---|---|
| M1 | `_REDIRECT_REQUEST_TIMEOUT = 600` (cloud_quota.py:232) | KILLED: `test_production_handler_timeout_is_short` fails (test_oauth_hardening.py:397) |
| M2 | `_REDIRECT_REQUEST_TIMEOUT = 0` | KILLED: `test_production_handler_timeout_is_short` and `test_first_sign_in_response_wins_over_a_later_one` fail |
| M3 | remove the session-baseline fixture, keep per-test | Suite stays 509/0 failures, but the scratch live folder was left with `state.json` (25 bytes, `{"column_widths": {}}`): some test's worker thread or an undone per-test patch writes through the unredirected path. Session layer is NECESSARY. The writing test was not identified (not verified) |
| M4 | remove the three `main.*` patches (both layers) | KILLED: `test_real_writers_land_in_the_test_folder` fails (test_secrets_isolation.py:15, path outside test folder). Full run also leaked `state.json` and `quota_history.json` into the scratch live folder, which shows the patches are needed |
| M5 | remove the per-test layer only (session kept) | KILLED: only `test_real_writers_land_in_the_test_folder` fails (path is `secrets_baseline0/state.json`, outside tmp_path); full run leaves the scratch live folder empty. So the per-test layer is guarded only by that one test, and nothing else notices if it goes |
Baseline (unmutated) full run with scratch `HOME`: scratch live folder empty after the run (0 files), in all four full runs below.

### Test quality
- `test_production_handler_timeout_is_short`: can fail (M1, M2); pins the shipped value, not the patched one. It is a constant check, not
  behaviour (the handler's use of it is covered by `test_silent_connection...`); the bound 10 s is a judgement call, acceptable. No time or network use.
- `test_secrets_isolation.py`: real writers, not mocked except `run_cmd`; assertions can fail (M4, M5) and check `.exists()` as well as location.
  Minor: it does not assert `cloud_quota.TOKENS_FILE` etc., but conftest patches them identically and the existing oauth tests exercise them.
- Override: autouse fixtures run before the explicitly requested `isolated` fixture (test_oauth_hardening.py:24) and test-body patches, so tests that patch
  `SECRETS_DIR` / `_STATE_FILE` (test_overdue_cooldown.py:22, test_resizable_columns.py:30, others) override correctly; 509/0 failures confirms it.
  Caveat: tests that patch only `cloud_quota.SECRETS_DIR` (e.g. test_main_window.py:37, test_drive_split.py:109) leave `CREDENTIALS_FILE`, `TOKENS_FILE`,
  `MANUAL_ACCOUNTS_FILE` on conftest's `tmp_path/_secrets`, which is still a scratch folder, so safe (and better than before, when they fell back to the live files).
- Order dependence: test_oauth_hardening + test_secrets_isolation x5: 45 tests, 0 failures each time (exit 0). Full suite with files in reversed order and in a seeded
  random order (seed 7, explicit file lists; pytest-randomly absent): 509/0 failures each. Within-file order not shuffled (not verified).
- `import main` in conftest: 23 test files already import main at module level, so collection cost and import side effects are unchanged in kind. `main.py`
  creates no `QApplication` at import (a test creates it), and `QT_QPA_PLATFORM` is only read at app creation, so the `setdefault("offscreen")` lines in test modules
  still run in time. A run without `QT_QPA_PLATFORM` set in the shell was not tried (not verified). The only residual risk is that an import-time failure in main.py now fails every test at conftest load instead of the 23 files that use it (P3, informational).

### Full suite (`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -p no:warnings --junitxml=...`, scratch tree at e6ef87c)
| Run | HOME | tests | failures | errors | skipped | exit | files left in scratch live folder |
|---|---|---|---|---|---|---|---|
| 1 | scratch | 509 | 0 | 0 | 2 | 139 (known Qt teardown crash) | 0 |
| 2 | scratch | 509 | 0 | 0 | 2 | 139 | 0 |
| 3 | scratch, files reversed | 509 | 0 | 0 | 2 | 139 | 0 |
| 4 | scratch, files shuffled (seed 7) | 509 | 0 | 0 | 2 | 139 | 0 |
| 5 | real (after the scratch runs showed the fixture holds) | 509 | 0 | 0 | 1 | 139 | n/a, see below |
The skip count is 1 in the real-HOME run and 2 in the scratch runs; which skip is HOME-dependent was not investigated (not verified).
Live folder: `ls -l` of the real Application Support folder before and after run 5 is identical. This is NOT evidence on its own: the installed app (pid 66494) rewrites its
live files on its own timer, so live mtimes can move or stay for reasons unrelated to the tests. The evidence is the empty scratch live folders in runs 1 to 4 and M3 to M5.
Coverage of changed lines: not measured (no coverage tool configured); the mutation kills are the evidence. Model-calling checks: not applicable (no model in `## Models used` for this change).

### Ranked gaps
1. P3: the per-test layer is guarded by a single test (M5); acceptable since the session layer already holds the live folder.
2. P3: the test that writes `state.json` when the session layer is absent is unidentified.
3. P3: a conftest-level `import main` makes an import failure in main.py fail the entire suite (informational).

Overall: R1 and R2 PASS; no P0/P1/P2 open.

## Fifth pass at fa9cbb2 (QA engineer)
Playbook `docs/playbooks/qa-engineer.md`: status current, last-reviewed 2026-10-14 (not stale). Every run used a scratch HOME (`$S/fakehome`, `echo $HOME` checked); mutations were made in a detached `git archive HEAD` copy, the worktree is untouched apart from this file.

### Mutation table (conftest `_redirect` edited in the scratch copy; `pytest tests/test_secrets_isolation.py`)
| Redirect removed / changed | per-test layer only | session layer only | both | wrong file name (both layers) |
|---|---|---|---|---|
| CREDENTIALS_FILE | killed | SURVIVES | killed | SURVIVES |
| TOKENS_FILE | killed | SURVIVES | killed | SURVIVES |
| MANUAL_ACCOUNTS_FILE | killed | SURVIVES | killed | SURVIVES |
| WORKSPACE_REPORT | killed | SURVIVES | killed | SURVIVES |
| _SHOW_REQUEST_FILE | killed | SURVIVES | killed | SURVIVES |
Killed by `test_every_secrets_and_state_writer_lands_in_the_test_folder` each time. P3 (1) of the fourth pass is closed: all 5 paths are guarded in the per-test layer and in both.
Survivors:
- Session-only removal (5): the per-test layer masks it while a test runs, so the test cannot see the session layer. Not a gap for the live folder while the per-test layer holds; it is the residual P3 "session layer is unguarded" (it only matters for a worker thread outliving its test).
- Wrong file name (5): the test checks the folder, not the name, so a mis-named redirect inside scratch passes. Harmless for safety (still scratch); a P3 test-precision gap, fix by asserting `p.name` or the expected path.
Side effect: the "both" mutants wrote 5 files into the scratch live folder, which is the expected proof the leak is real without the redirects; folder emptied before the suite.

### Test quality
- The new test calls the real writers: `cloud_quota.save_app_credentials/save_tokens/save_manual_accounts`, `workspace_extra.write_report(..., main.WORKSPACE_REPORT)`, and `main._SHOW_REQUEST_FILE.write_text` (the last is a direct write, not production code, so it proves the path only, not the production writer in main.py ~6053-6059). Asserts existence and `tmp_path in resolve().parents`; can fail (mutants killed).
- Other import-time paths: all derived from `cloud_quota.SECRETS_DIR` at import in main.py are redirected (_STATE_FILE 1200, WORKSPACE_REPORT 1262, _QUOTA_HISTORY_FILE 1297, _INSTANCE_LOCK_FILE 6036, _SHOW_REQUEST_FILE 6053). Call-time uses (main.py 924, 1213, 1324, 5703-5705, 6059, 6135; lab_health.py 46, 637, 827, 1119) read `cloud_quota.SECRETS_DIR` and so follow the patch. Not under SECRETS_DIR: `main.AUTOSYNC_STATE_DIR` (main.py 4956, HOME-derived `git_autosync`), read-only via `autosync_state` (not verified that no test writes it). No unredirected SECRETS_DIR-derived path found.
- Stability: test_oauth_hardening.py + test_secrets_isolation.py x5: 46 passed each, 0 failures.

### Full suite (scratch HOME, `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -p no:warnings --junitxml=...`, scratch tree at fa9cbb2)
| Run | tests | failures | errors | skipped | exit | files left in fake live folder |
|---|---|---|---|---|---|---|
| 1 | 510 | 0 | 0 | 2 | 139 (known Qt teardown crash) | 0 |
| 2 | 510 | 0 | 0 | 2 | 139 | 0 |
Real HOME was not used. Coverage and model-calling checks: not applicable / not measured, as in earlier passes.

### Ranked gaps
1. P3: wrong-name redirects survive; assert the file names.
2. P3: session layer is not observable by any test (session-only removals survive); optional, a pytester/subprocess test.
3. P3: `_SHOW_REQUEST_FILE` is exercised by a direct write_text, not the production writer.

Verdict: first-pass items (1) and (2) of the fourth-pass P3s are PASS (closed). No P0/P1/P2 open. Overall PASS.
