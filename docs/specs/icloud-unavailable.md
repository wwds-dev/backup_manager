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
