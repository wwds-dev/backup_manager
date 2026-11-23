# Storage tiles: one size, no clipped text

Needs: define, design, build, verify, docs
**Problem.** On Storage the tiles had different heights, and the Proton Drive tiles cut their
last line ("(22-06-2026 22:10)", "app can use)") (owner screenshot, 2026-11-20).

**Success measure.** Every tile in the Storage row has the same width and height, and no label
or link button is clipped at any window width. `tests/test_tile_uniform_size.py` asserts both;
3 of 5 cases fail without the fix (mutation-checked by reverting `FlowLayout._layout`).

**Non-goals.** Wording, colours, tile width (stays 230), Overview gauges.

**Design.** Content is top-aligned; spare room sits below the link, not between lines.

**Architecture.** `FlowLayout` gives every item one cell: widest hint, and the tallest height any
item needs at that width (`heightForWidth`). `StorageTile` and `ICloudTile` end with a stretch.
No state, thread or network change.

**Approval.** Define: owner asked for it in chat, 2026-11-20 ("make all tiles the same size and
make sure no text is cut off").

**Phases skipped.** ADR, Secure, Comply, Launch (layout only; public tier). Not reviewed by a
second agent. Installed as v2.263 (2026-11-20).

## Verify log (2026-11-20)
Full suite green (one mode). Offscreen render checked by eye: four mixed tiles, equal size, all
text visible. Not checked on the Storage page of the installed app.
