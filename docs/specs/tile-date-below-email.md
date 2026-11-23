# Storage tiles: account date always below the email

Needs: define, design, build, review, verify, docs (the spec says it was not reviewed by a second agent: review is open)
**Problem.** macOS appends " (DD-MM-YYYY HH:MM)" to a re-created account folder
(`ProtonDrive-x@proton.me-folder (22-06-2026 22:10)`). The tile showed it on the email's line,
wrapping wherever the width ran out (owner, 2026-11-20).

**Success measure.** The tile's account line is the email, then the date on its own line
below it, for every tile that has one. Tiles without a date are unchanged.
`tests/test_tile_uniform_size.py::test_account_date_is_always_on_its_own_line_below_the_email`,
mutation-checked (fails without `account_display`).

**Non-goals.** Meaning of the date, Overview gauge wording (newline folded to a space there).

**Architecture.** `account_display()` in `main.py`, used by `StorageTile`. Layout only.

**Approval.** Owner asked in chat, 2026-11-20. **Phases skipped.** ADR, Secure, Comply, Launch,
second-agent review (display text only; public tier).

## Verify log (2026-11-20)
Full suite green. Not built or installed yet.
