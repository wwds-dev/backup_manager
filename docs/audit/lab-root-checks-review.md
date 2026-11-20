# Code review: lab-root-checks (range 2c7b7f6..3a75974)

Independent read-only review by the `code-reviewer` agent, 2026-11-20 (not the author). Saved by the
orchestrator from the agent's report. Playbook `code-reviewer.md` current (last reviewed 2026-10-14).

Evidence: pytest on `test_lab_root_checks.py`, `test_workspace_extra.py`, `test_workspace_dialog.py`: 73 tests, 0
failures (junitxml; the process still exits 134, the known interpreter-exit crash). `scan` against the real lab,
read-only: R1 `build_marker.py`, `runners`, `setup_github.command`; R6 `lab_dashboard_data.json`,
`lab_projects_monitor_page.html`. Not verified: the window on screen, `open -R` on a real finding, the installed
app, a lab over 50,000 entries.

**Verdict: approve to merge after the P2 is fixed and the owner reads P3-1 to P3-4. No P0 or P1.**

## P2
**P2-1. Show in Finder does nothing on every R6 row, and the failure is silent.** `main.py:3644`. R6 rows are
broken symlinks, so `open -R <dangling>` prints "does not exist" and exits 1; `run_cmd` returns `(1, "", err)` and
the lambda discards it. Both real findings today are R6 rows. Fix: when the path no longer exists
(`os.path.lexists` false or a broken link) reveal the parent with `["open", dirname(p)]`; show a non-zero result in a
status label or tooltip. Test gap: no test for either case.

## P3
- **P3-1** R5 is a prefix match, not "exact": `` `labx` `` in AGENTS.md hides a missing project `lab`
  (`lab_root_checks.py:223`). Faithful port of Folder Audit. Fix: require a closing delimiter, or at least correct the
  Build wording and add a test documenting the behaviour.
- **P3-2** An empty `_to_delete/` is reported twice (R3 and R4); a broken symlink named `_to_delete` gives R3 and R6;
  a symlink to a folder is described as "not a folder" (`:194-212`). Fix: R4 skips `_to_delete`; R3 skips broken links;
  reword.
- **P3-3** NFC against NFD: a documented non-ASCII name is flagged R1 when the disk name is NFD (`:177`). Fix:
  normalise both sides to NFC, for R1 and R5; add a test.
- **P3-4** If `AGENTS.md` or `README.md` is a symlink the table floods with false R1 rows (`:52-61`). Fix: one visible
  row "AGENTS.md is a symlink and was not read" and suppress R1 and R5.
- **P3-5** An exception in `scan` loses the whole Workspace dialog and the weekly report (`main.py:3459-3463`,
  `workspace_extra.py:289`). Fix: wrap the lab-root call; return `[]` or one "lab root scan failed" row.
- **P3-6** Sizes can be wrong without a marker: `os.walk` with `onerror=None` shows an unreadable folder as 0 B; at the
  cap, R3 prints "N files, oldest M days" from a partial walk; the docstring says symlinks inside a folder are counted
  but dir symlinks are skipped (`:129-146`). Fix: a "partial" flag from `_measure`; "at least N" or "size unknown";
  drop count and age from the R3 text when capped; fix the docstring.
- **P3-7** A vanished entry is reported with size 0 and age 0 (`:150-152`). Fix: `None` size and age, or drop the
  finding; test with a patched `_lstat`.
- **P3-8** R5 sizing walks whole projects (`.venv`, `node_modules`) up to the cap (`:154`). Fix: do not measure R5 rows.
- **P3-9** A symlinked `active/` is followed (`:215`, `:229`). Fix: skip unless `_is_real_dir`.
- **P3-10** UI: `resizeRowsToContents()` before layout may clip the Why column; `run_cmd` (60 s) on the GUI thread;
  the table is a snapshot. Cosmetic, not verified on screen.
- **P3-11** Test gaps: unicode names, a regular file named `_to_delete`, an empty `_to_delete`, a permission error, a
  vanished file, R2 on a dotfile (`.hid.bak`), exactly-cap and nested cap, age rounding and future-mtime clamp,
  `show_workspace` surviving a raising scan, a click on a broken path.

## The five deliberate differences
All accepted: (1) R2 patterns (also note two differences not in the Build list: R2 ignores symlinks; project-level
stale patterns are dropped, so retiring Folder Audit loses that coverage: tell the owner); (2) `CLAUDE.md` not read;
(3) R5 match accepted but the label is wrong (P3-1); (4) R1 skips R4/R6 findings; (5) symlinked docs not read, but
needs a visible signal (P3-4).

## The two real R6 findings
Right to flag. `lab_dashboard_data.json -> dashboards/lab_dashboard_data.json` and
`lab_projects_monitor_page.html -> dashboards/lab_projects_monitor_page.html` (both 10 Oct) have no target; the real
files are in `dashboards/lab_monitor/`. Leftovers of `docs/dashboard_cleanup_plan.md` step 4. No consumer reads the
root links (grep). Delete or retarget; lab `README.md:314` still names the old path. Not verified: the monitor server.

## README, TODO, spec
README accurate except "never follows a symlink" (one `os.stat` goes through each link; P3-9). The spec's "R5 exact
match" is wrong. The 40/40 mutation table was self-run and not re-run by the reviewer.
