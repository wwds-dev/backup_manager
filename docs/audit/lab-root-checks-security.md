# Security review: lab-root-checks (range 2c7b7f6..3a75974)

Independent read-only review by the `security-engineer` agent, 2026-11-20 (not the author). Saved by the
orchestrator from the agent's report. Playbook `security-engineer.md` current (last reviewed 2026-11-11).

Method: read `lab_root_checks.py`, the `main.py` table and button, `workspace_extra.build_report`; ran `scan` and
`_measure` against throwaway fixtures under `/private/tmp`; one offscreen Qt render. Never ran `folder_audit.py`,
never scanned the real lab; fixtures deleted.

**Verdict: pass with findings. No P0, P1 or P2.** The spec's promises hold: read-only, no network, no subprocess, no
symlink followed in normal operation, bounded walks.

## What held
- Symlinked `AGENTS.md` pointing outside the lab is treated as empty (`lab_root_checks.py:55`). Links to `/`,
  `/Volumes`, an in-lab dir, a loop, a dangling link and a `-dash` link each listed once by their own `lstat`, never
  walked. A FIFO named `fifo.md` is listed, never opened.
- Names with a leading dash, `~`, space, newline, ESC, RLO, HTML text and 250 characters gave one finding each, no
  crash, JSON-serialisable. Pattern matching is linear (1-4 ms per 1,000 matches, adversarial names).
- Qt item text is not rich text (`<b>BOLD</b><img src='x'>` shown literally); tooltips use `_plain_tip`.
- `open -R` is a list passed to `subprocess.run` (no shell); the path is always absolute under `HOME/Documents/lab`,
  so a leading dash, space, newline or `~` cannot become an option.
- 120,000 files: `None` in 0.11 s; ~500 nesting levels in 0.05 s, 27 MB RSS; 2 MB of backticks in 0.05 s.
- `_write_private` unchanged (`O_NOFOLLOW`, mode 600); the existing report file is `-rw-------`.

## Findings (all P3)
- **P3-1** TOCTOU in `_read_doc` and `_measure` (`lab_root_checks.py:54-59`, `134`): `lstat` then `open()` by path; a
  swap to a FIFO blocks the scan worker forever (confirmed that opening a FIFO blocks); a swap to a symlink is
  followed. `os.walk` follows a symlink given as the top (confirmed: `_measure(<symlink to dir>)` walked the target).
  Fix: `os.open(p, O_RDONLY|O_NOFOLLOW|O_NONBLOCK)`, `fstat` and `S_ISREG`, `fdopen`; `lstat` again inside `_measure`.
- **P3-2** `os.stat` on a symlink can hang on a network or autofs target (`:121`), leaving the button on
  "Scanning…" and blocking later weekly scans (`main.py:3430`). Not verified on a real volume. Fix: only `stat`
  through links whose target is under the lab or home; otherwise "not checked".
- **P3-3** R3 reports "0 file(s), oldest 0 days" when `_to_delete/` is over the cap (`:197-201`, `146`). Fix: word it
  "more than 50,000 entries, not measured".
- **P3-4** `workspace_report.json` now carries absolute paths, names and raw `readlink` targets (`workspace_extra.py:289`,
  `lab_root_checks.py:162,235`); the `_maybe_weekly_scan` docstring (`main.py:3424`) still says "counts and sizes".
  The directory is 755 (predates this). Backed-up or synced: not verified. Fix: correct the docstring; state in README
  and spec that the report holds names.
- **P3-5** A bidi override in a name spoofs the Path column (`main.py:3640`); the tooltip keeps the raw character.
  Fix: replace Cc and Cf characters with `\uXXXX` in text and tooltip.
- **P3-6** Show in Finder runs `open -R` on the GUI thread, 60 s timeout, result ignored (`main.py:3643`, `800-805`);
  on a symlink row it may reveal the target outside the lab (not verified). Fix: short timeout, show the return code,
  worker thread or `QDesktopServices`.
- **P3-7** `build_report` couples the scan into the weekly report (`workspace_extra.py:289`): an unexpected
  exception loses the other counts. Fix: `try/except OSError` inside `build_report`.
- **P3-8** The walk cap bounds per directory only: `os.walk` lists a whole directory first; `_entries` for the root and
  `active/` is not capped; `_to_delete` is measured twice. Fix: `os.scandir` with a counter if a hard bound is wanted.

Informational: a root symlink to a directory is labelled "file" in the R1 text; every root dotfile is skipped by R1
(a design choice in the spec).

Not verified: the real GUI and a real `open -R` run; links to iCloud or network volumes; a real swap race (primitives
only); directories over 120,000 entries; whether `Application Support/Backup Control Center` is synced or backed up.
