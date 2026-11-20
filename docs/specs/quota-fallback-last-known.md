# Quota fallback: last known value, never local disk

**Problem.** When a connected Google Drive or Dropbox tile's live quota call fails for any
reason other than an expired login (400/401), `StorageTile.set_usage` shows the Mac disk's
free space instead (`main.py`, the "showing local disk" branch). The only hint is a small
"(local disk)" suffix, and the Overview gauge copies the number. On 2026-11-20 the owner saw
every storage card read 348.8 GB free of 926.4 GB (the Mac disk) while all three accounts
were connected and returned real quota seconds later. The app displays a number that is
true of a different thing.

**User.** The owner, reading Overview and the storage tiles.

**Success measure.** With a connected account whose quota call raises, returns nothing, or
times out, the tile and the Overview gauge never show local-disk numbers:
- a previous sample exists in `quota_history.json`: the tile shows that sample's usage with
  "as of <time>" (time only if today, otherwise date and time);
- no sample exists: "Account quota unavailable", empty bar, gauge "—".
Tests cover both and are mutation-checked. Unconnected tiles are unchanged (local disk,
labelled "(local disk)", with the "Connect for account quota" link).

**Non-goals.** Retrying or background refresh of a failed call. Showing the error text. Any
change to the expired-token path, to iCloud, or to the Local Disk tile.

**Design.** Detail text only: `… used of …  (account quota, as of 13:17)`. No new widget.

**Architecture.** One Qt-free helper in `main.py` next to the quota history functions:
`_last_known_quota(account_key)` returns `(used, total, ts)` or `None`; and
`_format_as_of(ts, now)`. `set_usage` uses them in place of the local-disk fallthrough when
the account is connected. No new state, network or file writes.

**Phases skipped.** ADR (no state, concurrency or boundary change), Secure (no new network,
secret, auth or input: reads the existing local history file), Comply and Launch (public
tier, no claim or data-flow change).
