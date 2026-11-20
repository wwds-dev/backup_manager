# Cloud quota off the UI thread (audit H2)

**Problem.** `StorageTile.__init__` calls `set_usage()`, which calls `cloud_quota.quota()` and
`cloud_quota.dropbox_account_email()` synchronously: a token refresh plus an API call per connected
account, 20 s timeout each, on every Storage refresh (5-minute timer, theme change, network back,
Refresh all). The window freezes for up to 40 s per account, and the slow call is the likely reason a
transient failure ever shows (the 2026-11-20 incident). It breaks the lab hard rule: no network on the
UI thread.

**User.** The owner, reading Overview and the storage tiles.

**Success measure.**
- Building a connected `StorageTile` with a fake 5 s quota call returns in well under 1 s (measured and
  recorded in the TODO row); a test records the thread each `cloud_quota` call runs on and asserts none
  is the GUI thread.
- The tile shows the last known sample at once ("as of <time>"), or "Checking account quota…" when none
  exists, then the live value when the worker finishes. Overview gauges follow.
- Everything shipped in v2.137 holds: failed call → last known "as of" or "Account quota unavailable",
  never local-disk numbers for a connected account; 400/401 → reconnect button; unconnected tiles →
  labelled local disk. `test_quota_fallback.py` and `test_tile_windows.py` keep their assertions (they
  wait for the worker first).

**Non-goals.** Retry or backoff; coalescing overlapping refreshes; moving `quota_history.json` writes
off the UI thread (small local file); iCloud and Local Disk tiles; the expired-token path.

**Design.** Detail text only. While fetching, a connected tile shows the last-known line (same text as
the failure fallback) or "Checking account quota…" with an empty bar. No new widget.

**Architecture (GATE: threading and state).**
- `StorageTile.set_usage` is split. `set_usage` renders synchronously from local data only (last known
  sample, or the unconnected/local-disk/not-mounted branches, unchanged) and, for a connected account,
  starts one `CallWorker` via `replace_worker(self._quota_worker, new)` (so `start_thread()` stays the
  only start path; no `terminate()`). The worker's function only does the network calls and returns a
  plain tuple `(email, result, error_text)`; it catches its own exceptions (CallWorker would turn them
  into `None` and lose the 400/401 text) and touches no widget.
- `_apply_quota(token, payload)` runs on the GUI thread via `done` and holds the existing
  result/expired/last-known logic, then emits `measured`.
- **Dead tile:** `StorageCard.refresh()` calls `tile.retire()` on every old tile before dropping it.
  `retire()` sets `_retired`, disconnects the worker's `done`, and bumps the token. `_apply_quota`
  also returns if `_retired` or the token is stale, and `RuntimeError` from a deleted C++ object is
  caught. The worker keeps running inside the keeper until it finishes (no abort, no crash).
- **Stale result:** each `set_usage` call increments `_quota_token`; `replace_worker` cuts the older
  worker's signal and `_apply_quota` ignores any payload whose token is not current. A result from an
  older refresh can never overwrite a newer one. A new refresh builds new tiles, so the old tile's
  result is dropped, not applied.
- **Gauges:** every `StorageTile` emits `measured` (like `ICloudTile`); `StorageCard.refresh` connects
  it to `StorageCard.updated`, which already drives `OverviewPage.refresh_gauges`.
- State touched: tile-local `_quota_worker`, `_quota_token`, `_retired`. No new file, no boundary change,
  so no ADR. Cost: overlapping refreshes may run several workers at once (each ≤ ~40 s); accepted.

**Phases skipped.** ADR (no boundary change), Secure (no new network surface: the same two calls, now
off-thread; no secret, auth or input change), Comply and Launch (public tier, no claim or data-flow
change). Document is a TODO row and spec log (no CHANGELOG file in this app).

## Build and review log (2026-11-20)
- Architect gate approved by the owner ("Approve"). Built as specified, plus after review: a `_checking`
  flag so the Overview gauge says "N checking" instead of "N unavailable" mid-fetch; a cancel event so a
  retired or superseded fetch skips its remaining network calls; `set_usage` invalidates any fetch in
  flight; `_reconnect_done` returns on a retired tile; a worker that dies without a result renders
  "Account quota unavailable".
- Measured: `StorageTile` build with a fake 5 s `quota()` returns in 0.001 s.
- Review (code-reviewer, read-only): no P0/P1; P2/P3 above fixed. Full suite green; 8 mutations caught.
