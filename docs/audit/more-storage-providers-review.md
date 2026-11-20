# Review: spec `more-storage-providers` (Foundry phase 6)

Scope: `git diff main...claude/wizardly-payne-caa30e` (cloud_quota.py, main.py, 4 new test files, spec). Read-only review by the `code-reviewer` agent; report saved by the orchestrating session. Date: 2026-11-20.

Test run (scratch detached worktree, main checkout's `.venv`, `QT_QPA_PLATFORM=offscreen`, `python -m pytest -q -p no:warnings`): 455 tests, 0 failures, 0 errors, 1 skipped, exit 0 (build log reported exit 139; not reproduced).

## Counts
P0: 0 · P1: 0 · P2: 2 · P3: 5. No blocking defect. Owner should fix or explicitly defer both P2 before Release.

## Findings

### P2-1: refresh in flight during disconnect recreates a token entry without `provider`
- `cloud_quota.py` `_store_refresh_token` (~150-158) and `_onedrive_access_token` (~520-535). `_store_refresh_token` writes `dict(tokens.get(account_key) or {})` even after the account was removed; `disconnect()` takes `_TOKENS_LOCK` but not the per-account refresh lock.
- Evidence (probe, fake `requests.post` calling `c.disconnect("A")` mid-refresh): `after: {'A': {'refresh_token': 'new'}} is_connected: True quota: None`.
- Result: account "connected" again with no `provider`; `quota()` returns None; tile shows "Account quota unavailable" with no reconnect button; revoked token back on disk.
- Fix: write only if the account still exists; also hold `_refresh_lock(account_key)` in `disconnect`. Add a test (none exists).

### P2-2: total of 0 shown as "unlimited plan"
- `cloud_quota.py` `onedrive_quota`: `total = int(q["total"]) if q.get("total") else None`. Probe: `total=0 -> (5, None)`; `_render_quota` then says "X used (unlimited plan)", a false claim. `quota.state` is neither read nor tested.
- Fix: treat 0 as unknown ("total not reported"); map to None only when the key is absent. `test_quota_without_total` covers only the absent key.

### P3-1: tooltip says "Photos" without "and other"
- `main.py:1841`: "Total minus Drive files; the API does not separate Photos from Gmail." Test `test_drive_split.py:198-199` guards label text only. Reword or narrow the claim.

### P3-2: stale copy
- `main.py:2433` ("Google Drive or Dropbox") in `AddAccountDialog`; docstrings `main.py:2422`, `cloud_quota.py:22`. Build from the registry.

### P3-3: two history reads per tile on the UI thread
- `main.py` `_last_known_quota` and `_last_known_split` each call `_newest_usable_sample` (loads `quota_history.json`). One read was already on main; the second is new. Fetch the sample once.

### P3-4: redirect handler accepts the first GET
- `cloud_quota.py` `_wait_for_redirect`: a stray local GET to `127.0.0.1:53789` without `state` ends sign-in with "state check failed". Local nuisance; Secure-phase point.

### P3-5: pre-existing, deferred to Secure
- `google_connect` / `dropbox_connect` return `resp.text[:200]` in error text and send no `state`; `save_app_credentials` uses non-atomic `_write_json`. Not a regression.

## Per-brief checks
1. **drive_split / Quota contract**: `cloud_quota.py:75-82` None, negative drive, or drive > used give `(None, None, trash)`; drive == 0 valid; trash never subtracted; `used` never None; tuple unpacking `main.py:1967` and equality with plain tuples hold. OK.
2. **Registry refactor**: same case-insensitive prefixes as main; late-bound dispatch keeps test patches working; `connect` keeps "Unknown provider"; `CloudAccountsDialog.save_credentials` merges. Existing suite passes. OK.
3. **OneDrive flow**: PKCE S256, no client secret; 32-byte state checked with `compare_digest` before exchange; errors are `HTTP <status> (<code>)` only; rotated token via `mkstemp` + `fchmod 0600` + `fsync` + `os.replace` under `_TOKENS_LOCK` (RLock) and a per-account refresh lock; no token/code logged. OK except P2-1.
4. **Threads**: no new `.start()` site (only pre-existing `main.py:1423`); `CallWorker` + `replace_worker`; failure shows last-known, never local disk (`test_tile_failed_call_never_shows_local_disk`). OK except P3-3.
5. **Proton / links / wording**: Proton tile hides bar, shows fixed text, no gauge slot; links only from `cloud_quota.web_link`; "Photos" wording see P3-1.
6. **Tests**: each claim has tests; gaps are P2-1, P2-2 and tooltip wording.

## Mutation check (re-planted in scratch worktree, restored after each)
| # | Mutation | Result | Failing tests |
|---|---|---|---|
| M1 | `drive < 0 or drive > used` -> `drive < 0` | Killed | `test_drive_split.py::test_split_negative_difference_gives_nothing`, `::test_tile_hides_split_when_invalid[result2]` |
| M2 | `with _refresh_lock(account_key):` -> `if True:` | Killed | `test_onedrive.py::test_overlapping_refreshes_use_the_rotated_token` |
| M3 | state check -> `if False:` | Killed | `test_onedrive.py::test_connect_rejects_bad_or_missing_state[...]` |
| M4 | Proton `bar.setVisible(False)` -> `True` | Killed | `test_tile_links.py::test_proton_tile_shows_no_number_no_bar`, `::test_manual_proton_tile_is_link_only` |
| M5 | rotated token not stored | Killed | `test_onedrive.py::test_refresh_stores_rotated_token_atomically`, `::test_overlapping_refreshes_use_the_rotated_token` |

## Not verified
- No live OneDrive/Google/Dropbox call or Entra registration; the `usageInDrive` formula is unchecked against a real account.
- Nothing visual: no screenshot, app not built or installed.
- The other 11 build-log mutants were not re-run.
- Overview gauge layout with a real fifth column (tested only with `FakeTile`).
- Whether older tests write to the live `~/Library/Application Support` folder.
- Python version for `str | None` in the `Provider` dataclass.
- `tests/test_thread_lifetime.py` passed but was not read.
- Non-JSON bodies in `_oauth_error_text`; a 200 with non-JSON would raise `ValueError` in `onedrive_connect` (no secrets in text).
- Entra loopback-port and Microsoft scope facts are marked "memory" in the spec; not re-checked against vendor docs.
