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
