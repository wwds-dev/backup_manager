# Review: icloud-unavailable (commit 029fc93, merged in 5bba361)

Date: 2026-11-20. Reviewer: `code-reviewer` agent (read-only, not the author). Written down
by the orchestrator. Scope: `DATALESS_ERROR` and `icloud_local_bytes()` (`main.py:915-950`),
the 3 new tests in `tests/test_main_window.py`, the tile worker (`main.py:1913-1995`).

**Verdict: no P0 or P1. Correct and safe to keep.** Four P3 items.

## Evidence
- `git show 029fc93`; read `main.py:803-808` (`run_cmd`), `911-950`, `1913-1995`.
- `.venv/bin/python -m pytest -rA tests/test_main_window.py -k icloud`: 17 passed.
- `du -sk /nonexistent_zz` under `LANG`/`LC_ALL` = C, de_DE.UTF-8, fr_FR.UTF-8: message stays
  English in all three (ENOENT checked; EDEADLK itself not).
- `os.strerror(errno.EDEADLK)` == "Resource deadlock avoided" == `DATALESS_ERROR`.
- `str(subprocess.TimeoutExpired(...))` contains no ": ", so the whole command line becomes the
  `err=` field.

## Checks that passed
- Parsing: macOS du writes `du: <path>: <strerror>`. `rsplit(": ", 1)[-1]` gets the message even
  when the path holds ": ". Exact, case-sensitive match is right (strerror text, nothing appended).
- Locale: macOS strerror is not localised and the app sets no LANG. A translated message would
  count as "other", so the card falls back to "at least" (safe).
- rc != 0 with empty stderr gives PartialBytes (test 3). Dataless plus other errors gives
  PartialBytes (test 2). Blank or odd stderr lines count as "other" (safe). A timeout gives
  None, so the card shows "Unavailable". Garbage output gives None.
- `du -s` prints its total only when it finishes, so rc != 0 with only dataless errors comes from
  a complete run.
- Threads: only `ICloudTile._Worker.run` calls it, started with `start_thread()`
  (`main.py:1969`). There is no bare `.start()` or `terminate()` and no UI access.
  Invariant held.

## Core assumption: does EDEADLK mean "nothing local"? (from the reviewer's knowledge, not checked against Apple docs)
du walks with `lstat` and never opens files, so a cloud-only *file* is counted with 0 blocks and
gives no error. EDEADLK comes from listing a dataless *directory* that the system will not
download. That directory has never been listed on this Mac, so nothing under it is local. A
partly downloaded file causes no error, and its local blocks are counted. du takes no locks, so
there is no other plausible EDEADLK source.
Remaining risk (low, not verified): a macOS version where a directory stays dataless while some
of its children are on disk. That total would be understated but shown as exact.

## Findings
1. **P3, log hygiene: the "no paths" claim is false.** `main.py:936-938`.
   - `out=` holds the tail of du's stdout, `16428\t/Users/<user>/Library/Mobile Documents`, so
     the home path and account name are in `icloud_du.log`.
   - On timeout, `err=` holds the full du command line.
   - A file name containing a newline splits a stderr line, and the fragment can land in `err=`.
   - Most of this predates 029fc93, but the docstring (`main.py:927`) and the spec addendum say
     "no paths". The log is mode 0600 and stays on this Mac.
   - The test only asserts `"/x/a" not in log`.
   - Fix: log only the number from `out`. Log `err=` only from lines starting with `du: `. Assert
     `"/x" not in log`.
2. **P3, docs: the comment overstates what fails.** `main.py:915-916` and `923-925` say
   cloud-only *items* fail with EDEADLK; only cloud-only *directories* do. The result is right, but
   a maintainer could "fix" it wrongly. Fix: reword as "dataless directories cannot be listed
   without downloading; nothing below them is local".
3. **P3, test gap: one mutation survives.** At `main.py:930`, changing
   `e != DATALESS_ERROR` to `DATALESS_ERROR not in e` passes all tests. Fix: add a test with
   stderr `du: /x/a: Resource deadlock avoided extra` that expects PartialBytes.
   - Caught by the tests: removing the dataless branch, changing the constant, removing
     `not other`, removing `errors and`, `rsplit`→`split`, removing `rc == 0`.
4. **P3, process: phase order.** 029fc93 was merged and installed (v2.166) before this Review.
   AGENTS.md puts Review before Verify and Release. No defect resulted. Next time, review
   before merging.

## Orchestrator note (outside the reviewer's scope)
At 18:48 on 2026-11-20 the live `~/Library/Application Support/Backup Control Center/icloud_du.log`
was overwritten in the *old* format (no `not_downloaded=` field):
`rc=1 secs=0.0 out='' err='Operation not permitted'`.
- The running app (pid 96488, started 17:32, window title v2.166) writes the new format. So
  the line came from older code in another checkout: one of the worktrees
  `docs-more-storage-providers`, `icloud-unavailable-ad1e50`, `nice-agnesi-fa7204`,
  `wizardly-payne-caa30e` or `zealous-burnell-c2116b`. A test run or a run from source there
  wrote to live app data.
- That process lacked Full Disk Access, hence "Operation not permitted".
- This breaks the test bar ("a run never touches live data") on those branches, and it destroys
  the log evidence the spec relies on. Whether *this* branch's suite touches the live file is
  checked in the verify log.
