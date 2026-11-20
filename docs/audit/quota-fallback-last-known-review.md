# Review: quota fallback, last known value (code-reviewer, 2026-11-20)

Spec: `docs/specs/quota-fallback-last-known.md`. Verdict: no P0, no P1. Report written by the
reviewer and saved by the orchestrator (the reviewer is read-only).

**Correct:** failed call no longer reaches the local-disk branch; the 400/401 path and
unconnected tiles are unchanged; quota-only tiles; sample validation (total 0, negative used,
missing keys); the "no sample" gauge shows "—"; timestamps never raise.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | P2 | A stale value looks fresh on the gauge and tile: "as of" is only in the small detail line; sample age is uncapped | Deferred (TODO row) |
| 2 | P2 | Gauge for several accounts hid an unavailable one | Fixed: detail adds "N unavailable" |
| 3 | P2 | Tests missed the gauge copy path, `quota_only` with no path, real `requests` errors, the "as of" text, the bar value | Fixed: tests added |
| 4 | P3 | Malformed history (`Infinity`, top-level list, non-list samples) could raise inside the tile constructor | Fixed: helper and loader tolerate them; test added |
| 5 | P3 | `"400" in str(e)` can mistake a network error for an expired token (existing code, spec said unchanged) | Deferred (TODO row) |
| 6 | P3 | A year-old sample prints no year; unparseable ts prints "earlier" | Deferred |
| 7 | docs | README and TODO not updated | Fixed |
