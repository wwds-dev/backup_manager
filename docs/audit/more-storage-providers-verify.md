# Verify: spec `more-storage-providers` (Foundry phase 7)

- Spec: `docs/specs/more-storage-providers.md`
- Commit under test: `4965f9d` (scratch detached worktree, mutated and restored only there)
- Date: 2026-11-20 · Role: qa-engineer
- Playbook `docs/playbooks/qa-engineer.md`: `last-reviewed: 2026-10-14`, `status: current` (37 days, not stale).

**Read first: this verifies 4965f9d WITHOUT the Build session's P2 and tooltip fixes. They have not landed.** Both P2 findings and the Photos tooltip are reproduced below on this commit and are still open. Verdict: **FAIL until the two P2 and the tooltip are fixed and re-verified** (0 P0/P1, 3 failing or weak Success-measure points, 1 live-data issue that predates this work).

## 1. Success-measure verdict per bullet

All test commands: `QT_QPA_PLATFORM=offscreen <venv python> -m pytest -q -p no:warnings <file>` in the vwt dir. Targeted run of the 7 relevant files: `113 passed`.

| # | Bullet | Evidence (test) | Verdict |
|---|---|---|---|
| 1 | OneDrive in Add Account | `test_provider_registry.py::test_add_account_combo_lists_quota_providers` (no explicit `"onedrive" in keys`; it counts quota providers, so removal is caught indirectly, mutation M6 killed) | pass (weak assertion) |
| 2 | OneDrive tile "X used of Y" | `test_onedrive.py::test_tile_renders_used_of_total` (asserts "used of", "account quota", `pct == 25`) | pass |
| 3 | Mounted `OneDrive-*` gets Connect link; mount prefix | `test_mount_prefix[3 names]`, `test_mounted_unconnected_tile_has_connect_link`. Names tested all contain a dash; a bare "OneDrive" folder is untested (M13 survived, near-equivalent) | pass |
| 4 | Refresh stores rotated token | `test_refresh_stores_rotated_token_atomically` (token, other entries kept, mode 0600, no temp files), `test_overlapping_refreshes_use_the_rotated_token`; M10 and reviewer M5 killed | pass |
| 4b | ...and a disconnect during a refresh | no test. Throwaway probe: after disconnect mid-refresh `tokens.json` = `{'OneDrive-Personal': {'refresh_token': 'new'}}`, `is_connected: True` (revoked token back on disk, no `provider`) | **fail** (P2-1, reviewer's, reproduced) |
| 5 | 400/401 shows reconnect | `test_onedrive.py::test_tile_401_shows_reconnect`, `test_quota_fallback.py::test_expired_token_path_is_unchanged`, `test_quota_401_raises_with_status`; M4 killed. Detection is a substring test on `str(e)` (`main.py` `_render_quota`: `"400" in quota_error`), pre-existing design | pass |
| 6 | Failed call shows last-known, never local-disk | `test_quota_fallback.py::test_failed_call_shows_last_known_sample_not_local_disk`, `test_real_network_errors_do_not_show_local_disk`, `test_onedrive.py::test_tile_failed_call_never_shows_local_disk`; M7 killed by 6 tests. The OneDrive test has no history so it proves "no local disk" and "unavailable", not last-known (that is covered by the Google and fallback tests) | pass |
| 7 | OneDrive total 0 / unlimited | not in the bullets but it is a false claim on the tile. Throwaway probe: Graph `{"used":5,"total":0,"state":"exceeded"}` gives `quota == (5, None)` and tile text `'5.0 B used  (unlimited plan)'` | **fail** (P2-2, reproduced) |
| 8 | Split shown with `usage`, `usageInDrive`, `usageInDriveTrash` | `test_drive_split.py::test_tile_shows_two_lines`, `test_google_quota_reads_drive_and_trash`; M9 killed | pass |
| 9 | Split hidden when `usageInDrive` absent or difference negative | `test_tile_hides_split_when_invalid[3 params]`, `test_split_missing_drive_gives_nothing`, `test_split_negative_difference_gives_nothing`; reviewer M1 killed | pass |
| 10 | Trash never subtracted | `test_split_trash_is_passed_through_not_subtracted`; M14 killed | pass |
| 11 | "Photos" never without "and other" | label text passes (`test_photos_never_alone`). **The tooltip fails it:** throwaway probe found `('Photos, Gmail and other 30.0 B', 'Total minus Drive files; the API does not separate Photos from Gmail.')`; "Photos" appears in `main.py` `_set_split` tooltip without "and other". The test only scans label text | **fail** (P3-1, reproduced; strictly breaks the bullet) |
| 12 | Last-known keeps the split "as of" | `test_failed_call_shows_old_split_as_of`, `test_last_known_split_follows_the_same_sample_as_last_known_quota`, `test_history_keeps_split_and_old_samples_still_read`; M1 and M5 killed | pass |
| 13 | Proton tile: no number, no bar, no gauge | `test_proton_tile_shows_no_number_no_bar` (fixed text, no digit, `bar.isHidden()`, `pct is None`, `disk_usage_for` raises if called), `test_manual_proton_tile_is_link_only`, `test_proton_never_gets_a_gauge`; M3 killed, reviewer M4 killed | pass |
| 14 | Every tile has its own link, from the registry only | `test_every_tile_has_exactly_one_open_link` (4 tiles), `test_unmounted_tile_opens_registry_url`, `test_link_never_uses_an_api_value`, `test_every_registry_url_is_https_literal`, `test_google_link_authuser` (injection string yields no authuser), `test_icloud_tile_link`; M2 killed (specifically by `test_link_never_uses_an_api_value`). Note: a mounted tile with an unrecognised provider (`provider None`) gets no link; not a spec case, not tested | pass |
| 15 | Quota off the UI thread | `test_quota_off_ui_thread.py::test_no_network_call_runs_on_the_gui_thread` (records thread ids), `test_tile_builds_fast_while_the_quota_call_is_slow`; `grep` of `main.py` shows only one call site, inside the `CallWorker` closure (line 1926; `account_email` at 1920; `connect` at 2270 is in `ConnectWorker`); `test_thread_lifetime.py` passes. The test exercises Dropbox only; Google and OneDrive use the same closure | pass |
| 16 | Full suite green | see section 3 | pass (one mode) |
| 17 | New logic mutation-checked | see section 5: 14 new mutants, 12 killed, 2 survived | pass with findings |

## 2. Test quality
- Fakes, no network: `test_onedrive.py` autouse fixture replaces `requests.get/post` and `webbrowser.open` with an `AssertionError` raiser and redirects `SECRETS_DIR`, `TOKENS_FILE`, `CREDENTIALS_FILE`, `MANUAL_ACCOUNTS_FILE` and `_QUOTA_HISTORY_FILE` to `tmp_path`. `test_tile_links.py` makes `quota()` raise and captures `run_cmd`. `test_drive_split.py` patches `requests.get` per test only (no global network guard, acceptable). No model is called (app-context `## Models used`: None), so the live-eval rule does not apply.
- Meaningful: the overlap test uses a single-use-token fake that returns 400 on a stale token, so removing the lock fails it (reviewer M2). The atomic-write test checks the old file and the directory listing after `os.replace` fails.
- Weak spots: (a) `test_photos_never_alone` only inspects label text, so it cannot catch a tooltip (P3-1); it passes vacuously if no label contained "Photos" (the sibling test covers that). (b) `test_add_account_combo_lists_quota_providers` has no direct OneDrive assertion. (c) Tile-level `drive == 0` is untested (M11 survived). (d) `test_tile_failed_call_never_shows_local_disk` for OneDrive can pass on the placeholder alone. (e) No test for `total == 0`, disconnect-during-refresh, non-JSON 200 in `onedrive_connect`.
- Over-mocking: `test_tile_401_shows_reconnect` patches `cloud_quota.quota` to raise `HTTPError("401 ...")`, so the real OneDrive 401 text chain is covered separately by `test_quota_401_raises_with_status`; acceptable.
- No time dependence beyond a 0.05 s sleep widening a race window; thread tests use `wait(5000)`, not sleeps.

## 3. Full suite
Command: `QT_QPA_PLATFORM=offscreen <venv python> -m pytest -q -p no:warnings --junitxml=...` (run 5 times in total, two with JUnit):
- JUnit run 1 and run 2: `tests="455" failures="0" errors="0" skipped="1"`, 40 s. No flakiness seen.
- Skipped: `tests/test_appkit_guard.py` (needs the `lab_hub` checkout beside the repo, per app-context).
- The process exits **139 (segfault at Qt teardown) on every run**, as the Build log said. The review report said exit 0 and "not reproduced"; here it reproduced every time, and also on the base commit `d22d4c2` (run in a second scratch worktree, removed afterwards). Pre-existing, not a regression; results are read from the JUnit XML. A CI that uses the exit code will fail regardless (the owner should know).
- Modes: app-context lists one mode (`pytest`); nothing else to run.
- Coverage of changed lines: **not measured** (`pytest-cov` and `coverage` are not installed; app-context: no coverage target). Substituted by the mutation run and by reading the changed branches. Untested branches found: OneDrive `total == 0`, disconnect race, tile with `drive == 0`, `_oauth_error_text` with a non-JSON body.

## 4. Live app-data folder check
`~/Library/Application Support/Backup Control Center`: 26 entries listed with `stat -f '%m %z %N'` before and after.
- First run: `diff` shows exactly two changed files, `quota_history.json` (14025 to 15097 bytes, mtime changed) and `state.json` (mtime changed, size 469 unchanged). Everything else identical.
- The installed app (pid 96488, `/Applications/Backup Control Center.app`) was running, so I separated its writes from the suite's:
  - Idle for 20 s with no suite: no mtime change.
  - Each single test file run alone with the real HOME: no change in any of the 26 files.
  - **Full suite with a throwaway empty `HOME`:** `Library/Application Support/Backup Control Center/state.json` is created, containing `{"column_widths": {"t": [300, 100, 165]}}`, the fixture from `tests/test_resizable_columns.py`. The live `state.json` also contains this `"t"` entry. So a full-suite run writes `state.json` outside any `tmp_path`.
  - **Full suite with the real HOME:** `quota_history.json` gets a new sample for all three accounts (Dropbox, two Google) stamped at the suite's end minute; reproduced on 4 whole-suite runs, none on single files.
  - **Same behaviour on base commit `d22d4c2`** (state.json created under a fake HOME; quota_history.json changed under the real HOME). It is therefore pre-existing and not caused by this spec, and the new four test files alone, run under a fake HOME, write nothing.
- Not proven: that the suite makes a live Google/Dropbox call with the owner's tokens (the history samples suggest so; the running app could also write them). Cause is an order-dependent leak across files; not isolated to one test.
- Verdict: **fail for the repo-wide rule "a run never touches live data" (app-context Test bar), pre-existing**; the new tests comply.

## 5. Mutation check (new mutants; the reviewer's M1-M5 and the Build log's 16 not reused)
Each mutant planted by exact-string replace in the scratch worktree; tests run: the 9 relevant files (`test_drive_split`, `test_provider_registry`, `test_onedrive`, `test_tile_links`, `test_quota_off_ui_thread`, `test_quota_fallback`, `test_overview`, `test_thread_lifetime`, `test_replace_worker`); reverted with `git checkout -- <file>` after each.

| # | Mutation | Result | Killed by |
|---|---|---|---|
| M1 | `_append_quota_sample` ignores `drive`/`trash` keys | Killed | `test_drive_split::test_history_keeps_split_and_old_samples_still_read`, `::test_successful_call_records_split` |
| M2 | Open link takes its URL from the account label instead of the registry | Killed | `test_tile_links::test_link_never_uses_an_api_value` (plus 5 link tests) |
| M3 | `_OPTIONAL_GAUGES` gains `"proton"` (gauge slot for Proton) | Killed | `test_tile_links::test_proton_never_gets_a_gauge` |
| M4 | expired-token path removed (`expired = False`) | Killed | `test_onedrive::test_tile_401_shows_reconnect`, `test_quota_fallback::test_expired_token_path_is_unchanged` |
| M5 | failed call drops the old split (`_show_last_known` without split) | Killed | `test_drive_split::test_failed_call_shows_old_split_as_of` |
| M6 | Add Account omits OneDrive | Killed (indirectly) | `test_provider_registry::test_add_account_combo_lists_quota_providers` |
| M7 | failed call shows "used of ... (local disk)" | Killed | 6 tests incl. `test_onedrive::test_tile_failed_call_never_shows_local_disk` |
| M8 | OneDrive total read from `remaining` | Killed | `test_onedrive::test_quota_reads_graph` |
| M9 | Google split reads `usage` as `usageInDrive` | Killed | `test_drive_split::test_google_quota_reads_drive_and_trash` |
| M10 | rotation inverted (store only when unchanged) | Killed | `test_onedrive::test_refresh_stores_rotated_token_atomically`, `::test_overlapping_refreshes_use_the_rotated_token` |
| M11 | tile hides the split when `drive == 0` (`if not drive_files`) | **Survived** | none |
| M12 | reconnect also on "503" in the error | Killed | 6 tests, incl. `test_quota_fallback::test_failed_call_shows_last_known_sample_not_local_disk` |
| M13 | OneDrive mount prefix `"OneDrive-"` instead of `"OneDrive"` | **Survived** | none (near-equivalent: every tested name has a dash; a bare "OneDrive" folder would stop matching) |
| M14 | trash folded into "other" | Killed | `test_drive_split::test_split_valid`, `::test_split_trash_is_passed_through_not_subtracted` |

12 of 14 killed. After each mutant and at the end: `git status --short` in the vwt is empty, HEAD `4965f9d` (confirmed twice). The throwaway worktree for the base commit was removed (`git worktree remove`); no file in the repo or the real checkout was edited (`git status` of the real checkout shows only the pre-existing `docs/foundry/activity.jsonl`). Throwaway tests (`test_p2_demo.py`, `test_photos_demo.py`) live in the scratchpad `throwaway/` folder, not the repo.

## 6. Findings, ranked
| P | Finding | Evidence | Fix owner |
|---|---|---|---|
| P2-1 | Refresh in flight during disconnect re-creates the account with the revoked token and no `provider`; `is_connected` True, `quota()` None, tile "Account quota unavailable" with no reconnect button. No test. | throwaway `test_p2_1_...`: `TOKENS AFTER: {'OneDrive-Personal': {'refresh_token': 'new'}} is_connected: True`; code `cloud_quota.py` `_store_refresh_token`, `disconnect` | Build (open, not landed) |
| P2-2 | OneDrive `total == 0` is shown as "unlimited plan" (false claim; `quota.state` unread). | throwaway `test_p2_2_...`: `TILE TEXT: '5.0 B used  (unlimited plan)' quota: (5, None)`; `cloud_quota.py` `onedrive_quota` | Build (open, not landed) |
| P2-3 | The full suite writes to the owner's live `state.json` (test column-width fixture) and, with real tokens present, appends to the live `quota_history.json`; order-dependent, pre-existing since at least `d22d4c2`. Breaks the Test bar rule and pollutes the owner's settings. | section 4 | Build or a separate task; not caused by this spec; owner to decide to defer |
| P3-1 | Tooltip says "Photos" without "and other"; breaks the Success-measure bullet to the letter; the guarding test checks labels only. | `main.py` `_set_split`; probe in section 1 row 11 | Build (open, not landed) |
| P3-2 | Tile-level `drive == 0` untested (M11 survived): a valid split of 0 would be silently dropped; safe degrade. | M11 | Build: add one test |
| P3-3 | No direct "OneDrive in Add Account" assertion; bare "OneDrive" mount prefix untested (M13). | M6, M13 | Build: add one assertion each |
| P3-4 | Exit code 139 on every run (also on base); a CI keyed on the exit code cannot go green. | section 3 | owner / SRE |
| P3-5 | Reviewer's P3-2 to P3-5 (stale "Google Drive or Dropbox" copy, two history reads per tile, redirect handler accepts first GET, pre-existing `resp.text[:200]` echo) not re-tested here. | `review.md` | per review |

## 7. Not verified
- Branch coverage of changed lines (no `coverage` module).
- Any live call: OneDrive sign-in (no Entra app), real Google `storageQuota` formula (needs the owner's yes), Dropbox.
- Visual layout: no screenshot, app not built or installed; the fifth Overview gauge column is tested with `FakeTile` only.
- Whether the suite really sends live API calls with the owner's tokens (only the resulting history writes were observed); which test leaks to the live folder.
- Several accounts of one provider with the fullest-account gauge for OneDrive.
- The Build session's fixes (not landed); everything above is on `4965f9d`.
- Secure phase items (Files.Read scope width, `state` rollout to Google and Dropbox, atomic `app_credentials.json` write): out of QA scope.
- The "memory" facts in the spec (Entra loopback port, Graph scopes, `usageInDrive` semantics).
- Whether `str | None` in the `Provider` dataclass runs on the Python version the PyInstaller build uses (the venv ran it).
