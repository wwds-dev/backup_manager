# Review: keep every background QThread alive until finished (a85f126)

Reviewer: `code-reviewer` subagent, read-only, 2026-10-14. Author: a different session.

**Verdict: no P0 or P1 findings.**

| Sev | Where | Finding | Disposition |
|---|---|---|---|
| P3 | `main.py` `_ThreadKeeper.start` | The release lambda runs on the thread that connected it. A `start_thread()` call from a non-GUI thread would never be released (a leak, not a crash). The reviewer reproduced this; all current callers are on the GUI thread. | Precondition documented in the docstring. |
| P3 | `main.py` `replace_worker` | `old.done` is disconnected only while `old.isRunning()`. A `done` already queued can still arrive, but always before the new result, which overwrites it. This predates the commit. Not verified. | Deferred; harmless while results are idempotent overwrites. |

Checked clean: release happens on the GUI thread (a test guards this); no `id()` key collision (the id cannot be reused while the dict holds the object); no QThread `.start()` left outside `start_thread` (`cloud_quota.py:180` is a `threading.Thread`); no leak (a weakref to the thread was dead after release); a GUI-thread drop during `QThreadPrivate::finish` relies on Qt 6's `isInFinish` wait (not checked against the Qt source); `old.done.disconnect()` guards are correct.

Tests: the reviewer's mutation (the keeper holds nothing) fails all 4 lifetime tests with SIGABRT; the timeouts are 5 s against 0.05–0.3 s workers. The "tile reverted to `.start()`" mutation, which the reviewer listed as unverified, was run by the author before commit and failed `test_a_tile_deleted_mid_scan_does_not_take_its_worker_with_it`. Full suite: 100/100 clean runs.
