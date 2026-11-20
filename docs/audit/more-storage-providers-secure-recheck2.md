# Secure re-check 2: spec `more-storage-providers` at `c94c5fb` (Foundry phase 8, third pass)

Date 2026-11-20. Read-only. Scope: `git diff b0d4d32..origin/claude/happy-kapitsa-569013` (`cloud_quota.py` +27/-?, tests, spec fix log). Earlier passes:
`docs/audit/more-storage-providers-secure.md` (85ff446), `...-secure-recheck.md` (b0d4d32). Method: read the diff, loopback probes against a scratch copy (no provider
call, no real token), four relevant test files in a scratch worktree with a temporary `HOME`.

## Counts
P0: 0 · P1: 0 · P2: 0 · P3: 0 new. R-1, R-2 and R-3 are fixed. Only the first-pass P3-3 (disconnect on the UI thread) stays open.

## Status
| Finding | Status | Evidence |
|---|---|---|
| R-1 non-atomic claim | **Fixed** | `claimed` flag set under `claim` before the response is written (`cloud_quota.py:~281-287`, `nonlocal claimed`). Probe C (real + junk request fired together, 30 runs): **0 of 30** merged results (was 9 of 30). |
| R-2 any `code`/`error` ends the wait | **Fixed** | `_wait_for_redirect(..., state=state)`; a request whose `state` is missing or wrong gets 404 (compared with `compare_digest` on bytes, non-UTF-8 safe) and the listener keeps waiting. All three `*_connect` pass `state` (`:333,418,546`). Probe B: `?code=x` → 404, still waiting; then the real `?state=S&code=C` → 200 and `_redirect_code` → `('C', None)`. |
| R-3 negative `total` | **Fixed** | `max(int(...), 0)` in `google_quota` (`:383`) and `dropbox_quota` (`:490`); OneDrive already clamped. |

Unchanged and fine: stalled connection (probe A: real GET 200, returned in 0.5 s), 0700 folder and atomic 0600 writes, `state` + PKCE on all three providers, error text by code only, `requirements.txt`
untouched (`git diff b0d4d32..origin/claude/happy-kapitsa-569013 -- requirements.txt | wc -l` → 0), no new import, still HTTPS-only with timeouts and no `verify=False`.
`test_oauth_hardening.py`, `test_secure_followups.py`, `test_secrets_isolation.py`, `test_onedrive.py`: 91 passed; the temporary `HOME` stayed empty.

## Notes (no action required)
- A provider that returns an error redirect **without** `state` (spec-compliant providers include it) would now be ignored and the sign-in waits out its 180 s timeout instead of ending at once. Usability only, not a security issue; not verified against the three providers.
- The listener now returns 404 for non-matching requests, so a page cannot cancel a sign-in (R-2); it can still hold a thread for 5 s per connection (daemon threads, local only, unmeasured under flood).
- Still open from the first pass: P3-3, `disconnect()` waits for an in-flight refresh (up to ~20 s) on the UI thread (`main.py:1785,2398,2419`). Availability only.

## Not verified
- Full suite (520 tests, per the fix session) not re-run; 91 tests in four files were.
- No live provider call; Google `code_verifier` handling, error-redirect `state`, and the `Files.Read` scope fact (see the first report) remain from docs memory.
- The packaged `.app`, multi-user behaviour, and thread count under a connection flood.
