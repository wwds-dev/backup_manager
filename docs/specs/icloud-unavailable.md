# iCloud card: say why it is unavailable

**Problem.** On 2026-11-20 the Overview iCloud card (v2.137 and v2.141) showed "—" with
"Unavailable". Cause, measured: macOS denies reading `~/Library/Mobile Documents`
(`du -sk` prints "Operation not permitted", exit 1, instantly; `ls` fails the same), so
`icloud_local_bytes()` returns `None` and the tile writes "Unavailable". The text hides a
fixable cause: the app needs Full Disk Access.

**User.** The owner, reading Overview and the storage tiles.

**Success measure.** When reading the iCloud folder is denied (PermissionError), the tile
and the Overview gauge detail read "No access (Full Disk Access)" instead of
"Unavailable"; any other failure still reads "Unavailable"; a successful `du` is unchanged.
Tests cover denied, other failure and success, and are mutation-checked.

**Non-goals.** Granting the permission, opening System Settings, any change to the size
measurement, the bar, the last-known-value logic or other tiles.

**Design.** Detail text only. No new widget.

**Architecture.** One Qt-free helper `icloud_access_denied()` in `main.py` (an `os.listdir`
of the folder, True only on PermissionError). The tile worker calls it only when
`icloud_local_bytes()` returned `None` and emits a `DENIED` marker; `_apply_size` maps it to
the text. No new state, network, or writes.

**Approval.** Define: owner chose "Clear message" on 2026-11-20.

**Phases skipped.** ADR (no state, concurrency or boundary change), Secure (no new network,
secret, auth or input), Comply and Launch (public tier, no claim or data-flow change).

## Verify log (2026-11-20)
- Measured: `du -sk ~/Library/"Mobile Documents"` → "Operation not permitted", rc 1; `ls` same.
- Text is "No access (Full Disk Access)" (shorter than first drafted: tile is 230 px wide).
- Tests in `tests/test_main_window.py`; 3 mutations caught (PermissionError check, `size is None`
  guard, text mapping). Full suite green. Reviewer: no P0/P1; P2 gauge and worker tests added.
- Known limit (reviewer P2): a stale last-known gauge value hides a denial that begins mid-session.
- Not verified: the installed app really lacks Full Disk Access (only my shell was measured), and
  that the text fits the tile on screen.

## Addendum 2026-11-20: v2.156 still showed "Unavailable"
In the installed app the folder listing does not raise PermissionError, so `du` failed for
another reason. Owner's yes ("Yes, add logging"): `icloud_local_bytes()` now writes `rc`,
seconds, the tail of stdout and the first stderr line to `icloud_du.log` in the app-data
folder (overwritten each run; a write failure is ignored), and uses the last `du` line as a
partial total when `du` exits non-zero but printed one (it can understate the real size).
Tests: 4 in `tests/test_main_window.py`; 4 mutations caught.
Reviewer P1 fixed: a partial total is shown as "at least X (some folders unreadable)" (type
`PartialBytes`), never as a plain size. P2 fixed: the log keeps only the error text (no paths)
and is mode 0600; more tests (single-line rc 1, timeout, garbage). 4 more mutations caught.

## Addendum 2026-11-20: "at least 16.0 MB (some folders unreadable)" was misleading
Evidence: `icloud_du.log` from the installed v2.163 (14:44) reads `rc=1 out='16428\t…'
err='Resource deadlock avoided'`, so the card was no longer "Unavailable". EDEADLK is how
macOS refuses to open a cloud-only (dataless) iCloud item without downloading it; such items
use no local disk, so the printed total is the exact local cache. Fix: `icloud_local_bytes()`
treats `Resource deadlock avoided` lines as "not downloaded" and returns a plain total when
they are the only errors; any other error still gives `PartialBytes`. The log now records
`not_downloaded=` and `other_errors=` counts and the first other error (still no paths).
Tests: 3 new in `tests/test_main_window.py`; 3 mutations caught; full suite green.
Not verified: the card on screen after a restart (screen access declined this session), and
the EDEADLK-means-dataless reading against Apple documentation (based on known
`setiopolicy_np` materialization behaviour).
Verified 2026-11-20 17:32 on the installed v2.166 (restarted): `icloud_du.log` reads
`rc=1 out='16428…' not_downloaded=2 other_errors=0 err=''`, so the card shows the exact
total ("16.0 MB local cache"). The card text itself was not screenshotted.

## Review and Verify log (2026-11-20, independent pass on 029fc93 / v2.166)
Review: `docs/audit/icloud-unavailable-review.md` (`code-reviewer` agent, read-only). No P0 or P1.
P3 items:
- The log still holds the home path in `out=` and the command line on timeout, so "no paths" is
  not true.
- The comment says cloud-only *items* fail with EDEADLK; only *directories* do.
- A substring-match mutant survives the tests.
- Review ran after merge and install.

The EDEADLK-means-dataless reading was judged sound (du only `lstat`s files; only dataless
directories fail). It is still not checked against Apple documentation.

Verify (`qa-engineer` agent): **PASS.**
- Success measure shown through the real `_apply_size` (offscreen Qt, faked du rc=1,
  `16428`):
  - dataless-only → "16.0 MB local cache", log `not_downloaded=1 other_errors=0`
  - mixed → "at least 16.0 MB (some folders unreadable)"
- Full suite, `.venv/bin/python -m pytest -q`, 5 runs: 373 tests, 0 failures, 0 errors, 1 skipped
  (`test_appkit_guard.py`, no lab_hub beside the worktree), about 27 s.
  - Every run exits 139 (a segfault at exit after all tests pass). This is the known P2
    (`TODO.md:26`). It also happens at `029fc93^` and comes from `tests/test_workspace_dialog.py`
    alone.
- Mutations: 8 planted, 7 killed. Survivor M4: `not_downloaded={len(errors)}` (the mixed test
  does not assert the `not_downloaded` count). `main.py` was restored after each mutant.
- Gaps:
  - G1 (P2): assert `not_downloaded=1 other_errors=1` in `test_icloud_bytes_mixed_errors_stay_partial`.
  - G3 (P3): no single test asserts the exact text "16.0 MB local cache".
  - G4 (P3): no test for a non-English error message; a translated message would fall back to
    "at least", the safe direction.

Test isolation leak (found by the orchestrator, outside this spec):
- `tests/test_quota_off_ui_thread.py` overwrites the live
  `~/Library/Application Support/Backup Control Center/icloud_du.log` with a real `du` result
  ("Operation not permitted": the shell has no Full Disk Access). Each test file was run alone and
  the log's mtime checked; only this file changed it (19:00:46).
- Likely cause: an iCloud tile worker runs a real `du` after the test's `SECRETS_DIR` patch is
  undone.
- Older-format worktrees did the same at 18:48.
- This breaks the test bar and destroys the 17:32 log evidence above. It belongs to spec
  `quota-off-ui-thread`.

Screenshot: not taken. The app window (v2.166, pid 96488) is on another Space and the current
Space is full-screen, so background capture returned no image. Card text on screen is not
verified; the 17:32 log and the offscreen render above stand in for it.

Release check (`python3 docs/foundry/tooling/release_check.py .`):
- In this worktree: BLOCKED, because `docs/legal` is a link to the Foundry HQ that is not present in a
  worktree.
- In the main checkout at the same commit `ae66b37`: "legal gate clear (tier public) … clear:
  Release may start", rc 0.

## Review fixes 2026-11-20 (owner: "yes, have it fix the three P3 items")
Review report: `docs/audit/icloud-unavailable-review.md` (no P0/P1, four P3). Fixed P3-1 to P3-3;
P3-4 (phase order) left as is on the owner's word.
- P3-1 log hygiene: `icloud_du.log` now logs `total_kb=<number>` instead of du's stdout, and
  error text only from `du: <path>: <error>` lines (`_du_error_texts`); a timeout logs
  "timed out", any other stderr line (e.g. a file-name fragment) "unparsed error" and counts as
  an other error. Tests assert no `/x` in the log.
- P3-2: the comments now say cloud-only *directories* cannot be listed; nothing below them is local.
- P3-3: the dataless match stays exact; new test with "Resource deadlock avoided extra".
- Tests: 2 new, 3 tightened; 5 mutations caught (including the one the review found surviving).
  Full suite: no failures; pytest still exits 139 at interpreter teardown (known TODO item).
  The suite left the live `icloud_du.log` untouched (mtime unchanged).
- QA re-check (`qa-engineer` agent, read-only, commit 403cff1): pass. 12 crafted stdout/stderr
  inputs leak no path into the log; behaviour preserved (int / exact int / PartialBytes / None);
  `-k icloud` 19 passed; full suite 375 passed, 1 skipped, 0 failed (exit 139 at teardown, known);
  4 own mutations caught; `main.py` left identical to HEAD.
- New P3 from QA, not fixed (owner to decide): a file name containing both ": " and a newline can
  put a fragment of that name (never a full path, names cannot contain "/") into `err=`
  (`main.py:927`, logged at :957). Possible fix: log `err=` only for known strerror texts.
