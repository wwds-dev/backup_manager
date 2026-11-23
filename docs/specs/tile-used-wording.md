# Storage tiles: say "used of" everywhere

Needs: define, design, build, verify, docs
**Problem.** On Overview the big percentage of every card is "used", but the Mac disk detail
line reads "345.8 GB free of 926.4 GB" while Google Drive and Dropbox read "41.6 GB used of
100.0 GB". Same card row, two meanings (owner, 2026-11-20).

**User.** The owner, reading Overview and the storage tiles.

**Success measure.** A local-disk tile (Mac disk, and any unconnected mount) reads
"<used> used of <total>" (with the existing "(local disk)" suffix for an unconnected
provider tile); the free amount moves to the tile's tooltip ("<free> free"). The percentage,
bar and cloud tiles are unchanged. Test asserts the text and tooltip and is mutation-checked.

**Non-goals.** iCloud card wording, cloud tile text, colours, thresholds.

**Design.** Detail text only plus a tooltip. No new widget.

**Architecture.** One line in `StorageTile.set_usage` (`main.py`). No state, thread or network change.

**Approval.** Define: owner chose "used of" on 2026-11-20.

**Phases skipped.** ADR, Secure, Comply, Launch (no state, input or claim change; public tier).

## Verify log (2026-11-20)
Test in `tests/test_main_window.py`; 3 mutations caught (used vs free number, tooltip removed,
"free of" text). Full suite green. Not reviewed by a second agent (one-line text change);
not built or installed yet.
