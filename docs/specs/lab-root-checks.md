# Spec: lab-root checks (what is left of Folder Audit) in the Workspace section

Status: **Define approved by the owner 2026-11-20** ("Approve, report-only", recorded in `approvals.jsonl`; this settles open question 2 as report-only; questions 1, 3 and 4 stay as proposed: separate monthly review, keep R5, a table in Workspace). Built 2026-11-20 on `claude/lab-root-checks` (see Build and Verify below). Requested by the
owner 2026-11-20 ("merge whatever is useful of Folder Audit into Backup Control Center"; he chose "draft
spec for app rows"). Tier `public`. Builds on `docs/specs/workspace-cleanup.md` section 3, which split the
work: `folder_audit.py` keeps what sits at the lab root by name, the app takes what is measured. This spec
moves the by-name part into the app so `folder_audit.py`, its HTML report, its server and its fixers can go.
Not one of the in-flight specs (`secrets-vault`, `sidebar-redesign`, `quota-fallback-last-known`).
Owner rule 2026-11-20 ("testing first"): this is a new feature the owner asked for, so it may be drafted,
but build starts only on his word.

## Define

### Why
The owner wants a periodic check that his lab folder is still compact and logical, and that anything that
should be moved, consolidated, deleted or merged is surfaced. `lab/folder_audit.py` does that for the lab
root only, as a separate script with its own HTML page and local server. The lab dashboard catalog dropped
its entry on 2026-11-18, so the report is no longer reachable from Lab Hub.

### What Folder Audit still adds (measured 2026-11-20, read-only `run_audit()`)
Of its checks, only three produced a finding, all one kind: `build_marker.py`, `runners/` and
`setup_github.command` are "unexpected" at the lab root (not named in `AGENTS.md` or `README.md`). Stale
`*.bak` / `patch_*` files, a lingering `_to_delete/`, empty top-level folders, project `.git` / `.gitignore`
hygiene (16 projects) and Foundry file / `AGENTS.md` length (14 repos) were all clean, and the last two are
already covered by Lab Health and the Lab Overview architecture tab (`architecture_map.py`).

| Folder Audit check | Already covered by | In this spec |
|---|---|---|
| Unexpected files and folders at the lab root | nothing | **yes** (R1) |
| Stale `*.bak`, `*.orig`, `*~`, `patch_*`, `fix_*` at the lab root | nothing | **yes** (R2) |
| Lingering `_to_delete/` at the lab root | nothing | **yes** (R3) |
| Empty top-level folders | nothing | **yes** (R4) |
| Project named in `AGENTS.md` | nothing | **yes** (R5) |
| Project `.git`, `.gitignore`, broken symlinks | Lab Health (git column) covers git; the other two are not | **yes**, broken symlinks only (R6) |
| Non-Foundry repos, `AGENTS.md` over 150 lines | Lab Overview, Architecture tab | no |
| Disk-usage summary | Lab Health, Workspace | no |
| Fixers (quarantine to `_to_delete/`, purge, create `.gitignore`) | Trash gates in the app | **dropped** |
| HTML report, local server on 8877, `--serve` | n/a | **dropped** |

### Proposal
A **Lab root** table in the existing 🗂 Workspace section, report-only, below the backups and archive
rows. Each row: the finding (R1 to R6), the path, size, age and one line why it was flagged; a **Show in
Finder** button only. No tick box, no delete, no move: an item flagged here is acted on by the owner or an
agent (the same "stays manual" rule as `workspace-cleanup.md` section 5). The weekly report-only scan
(`workspace_report.json`) gets a `lab_root` list, so the report keeps working with the app closed. That
list holds file and folder names, absolute paths and symlink targets from the lab root (the report used to hold
counts and sizes only; it is a mode-600 file in the app's support folder).

Rules, ported as they are in `folder_audit.py`, with the names it reads kept in one Qt-free module
(`lab_root_checks.py`, next to `workspace_extra.py`):
- **R1** a root file or folder not mentioned in `AGENTS.md` or `README.md` and not a normal dotfile.
- **R2** `*.bak`, `*.orig`, `*~`, `patch_*`, `fix_*` at the lab root.
- **R3** `_to_delete/` exists at the lab root.
- **R4** an empty top-level folder (never inside `active/` projects).
- **R5** an `active/*` project not named in `AGENTS.md` (a prefix match, as in Folder Audit: the name only has to
  follow a backtick, so `` `labx` `` also covers a project `lab`).
- **R6** a symlink at the lab root or directly under `active/` that does not resolve.

Reads only: directory listings and the two Markdown files. No writes, no network, no subprocess. A flagged
symlink is listed, never walked or opened. (Define text; the fix pass below narrowed how "does it resolve" is
learned: by hand with `lstat`, only through the lab and `HOME`, never with one `os.stat` through the link.)

### Out of scope (stays as it is)
- `~/Documents` outside the lab (`Files`, `Business`, `Personal`, `Misc`...): the owner's purpose mentions
  the whole Documents folder, but `workspace-cleanup.md` section 5 already makes those report-only, and a
  "is this structure still logical" judgement is not a rule a script can make. See open question 1.
- Lab Overview's warnings, Lab Health, the Trash gates: unchanged.

### Success measure
- A test with a made-up lab folder (`tmp_path`) shows one finding per rule R1 to R6 and none for a clean
  lab; mutation-checked (each rule's condition flipped, a rule removed, the "normal dotfile" allowance
  removed, the symlink check made to follow links), every mutant killed.
- A real read-only run against `~/Documents/lab` reports exactly `build_marker.py`, `runners` and
  `setup_github.command` under R1 today, matching `folder_audit.py`'s output of 2026-11-20 (the owner may
  have named or moved them by then; the comparison runs the old script beside the new one on the same day).
- A test proves the module opens no file for writing and runs no subprocess.
- Suite green; no new dependency.

### Phases
Design: one table row set in an existing section, no new screen, so a short note in this spec is enough.
Architect: a Qt-free module with no state, threads or new boundary; skipped, unless the owner wants the
report written to a new file (it extends `workspace_report.json`). Secure: required (reads another folder's
listings, file names are untrusted input) but small. Comply, Launch, Release: not part of this change;
the owner asks for a release.

### After it lands (not part of this build)
Retire `lab/folder_audit.py`, its HTML and `dashboards/folder_audit/`; fix the references in the lab
`AGENTS.md` (the "Root scripts" line), `architecture_map.py` (script list) and the lab `README.md`. That is
a lab-repo change, done once the app row is released and the owner confirms Folder Audit may go.

## Open questions for the owner
1. **The "is this still logical" review.** A script finds only mechanical problems (three root items today).
   Your original aim, "is the Documents folder still compact and logical, should something be moved,
   redesigned, merged or deleted", is a judgement. Option: keep a monthly Claude review of `~/Documents`
   that writes a short report, separate from this app. Recommended yes, but it is not in this spec.
2. **Show in Finder only, or also "Move to Trash" for R2 and R3** (stale files, `_to_delete/`)? The spec says
   report-only. Trash moves would reuse the existing restore-record gates and add a write path to review.
3. **R5 (project not named in `AGENTS.md`)**: keep, or drop? It did not fire for any of the 16 projects on 2026-11-20.
4. **Where**: a table in 🗂 Workspace (proposed), or a separate row in Lab Health?

## Build (2026-11-20, engineer, branch `claude/lab-root-checks`)

Skipped phases: Design (a table in an existing dialog), Architect (Qt-free module, no state, thread or boundary;
`workspace_report.json` only gained a key), Comply, Launch, Release (not part of this change). Review and Secure
are still to do; version not bumped, app not built.

What changed:
- `lab_root_checks.py` (new, Qt-free): `scan(lab_root, now=None)` returns finding dicts `rule`, `path` (absolute),
  `rel`, `size` (bytes, `None` over the walk cap of 50,000 entries), `age_days`, `why` (the fix pass adds `partial`).
  Reads directory listings, `lstat` and `AGENTS.md` / `README.md` (opened read-only, only when a regular file, so a
  symlinked doc is not read). A symlink is sized and aged by its own `lstat` and never listed into, walked or opened;
  as first built, the only call that went through a link was one `os.stat` on the link to learn whether it resolves
  (R6); the fix pass replaced it (see Fix pass).
- `workspace_extra.build_report` adds `lab_root`; `_write_private` is unchanged. The `offered_*` totals are not
  affected (nothing there is offered).
- `main.py`: `show_workspace` scans the lab root in the existing `CallWorker` (so `start_thread()` is still the only
  start); `_workspace_ready` shows a `QTableWidget` (Rule, Path, Size, Age, Why, Show in Finder) after the archive
  rows: plain-text, non-editable, non-checkable cells, one button per row running `open -R <path>`.
- Tests: `tests/test_lab_root_checks.py` (25), 3 added to `tests/test_workspace_dialog.py`, 2 to
  `tests/test_workspace_extra.py`.

Choices to confirm (the spec text and `folder_audit.py` differ or are silent):
1. R2 uses Folder Audit's root patterns (`*.bak`, `*.bak_*`, `*~`, `*.orig`, `*.tmp`, `patch_*.py`, `fix_*.py`,
   `_patch*.py`), not the shorter `patch_*` / `fix_*` of the Define text, and, as the Define says, only at the lab root
   (Folder Audit also looked at each project's top level).
2. The docs read are `AGENTS.md` and `README.md` (the Define text); Folder Audit also read `CLAUDE.md` for names.
   `CLAUDE.md` is only `@AGENTS.md` today and is always allowed.
3. R5 keeps Folder Audit's match, a **prefix match** (a backtick directly before the project name, e.g. `` `proj` ``;
   `` `projx` `` also covers `proj`). A name seen only as `` `active/proj/` `` does not count, as in Folder Audit, so it
   would be flagged. Review P3-1 found the earlier label "exact match" wrong; the matching is unchanged on purpose.
4. R1 skips an empty folder (R4's) and a broken symlink (R6's), so one fact is one finding. Folder Audit already did
   this for empty folders.
5. R6 also covers the lab root, as the Define says. Folder Audit only looked under `active/`; this is why the real
   run below has two findings Folder Audit did not.

### Fix pass (2026-11-20, engineer, same branch, after the independent review and security review)

The owner approved fixing the findings below and only these (`docs/audit/lab-root-checks-review.md`,
`docs/audit/lab-root-checks-security.md`). Version not bumped, app not built, nothing merged. What changed, one line
per finding:
- **Review P2-1, secure P3-6 (part):** `main.py` `_finder_command`: Show in Finder runs `open <parent>` when the path is
  gone (`os.path.lexists` false), the link is broken, or the row is a symlink (it would reveal the target); otherwise
  `open -R <path>`. `_reveal_in_finder` runs it with a 10 s timeout and shows a non-zero result as the button text
  "Failed" and a tooltip ("open exited N: ..."); a later success restores the button.
- **Review P3-1:** R5 matching unchanged; the wording "exact match" is now "prefix match, as in Folder Audit" in this spec,
  the README and the test comment; `test_r5_is_a_prefix_match_so_a_longer_name_hides_a_missing_project` documents it.
- **Review P3-2:** R4 skips `_to_delete` (an empty one is R3 only); R3 skips a broken link (R6's); R3 words a file and a
  symlink as what they are ("as a file, not a folder", "as a symlink").
- **Review P3-3:** R1 and R5 compare names as NFC on both sides (disk name and doc text).
- **Review P3-4:** a doc that exists but was not read (symlink, FIFO, no permission) gives one visible `NOTE` row and
  R1 and R5 are skipped (before: a flood of false R1 rows).
- **Review P3-5, secure P3-7:** `lab_root_checks.scan_safe` turns an exception into one `NOTE` row ("The lab root scan
  failed (<ExcType>): nothing was checked"); `show_workspace` and `build_report` both call it.
- **Review P3-6, secure P3-3:** `_measure` returns `(bytes, files, oldest, partial)`; findings carry `partial`. Over the
  cap, an unreadable top folder or a swapped-in non-folder: size `None` ("size unknown"). An unreadable subfolder or a file
  that vanished: the size is a lower bound, shown "at least N". R3 text without count or age when not measured, "at least N
  file(s) seen" when partial. The docstring now says a symlink to a file is counted by its own size and a symlink to a
  folder is neither counted nor descended.
- **Review P3-7:** a vanished entry has `size` `None`, `age_days` `None`, `partial` True (the table shows "size unknown",
  "age unknown").
- **Review P3-8:** R5 rows are not measured (size `None`, age from the project folder's own mtime).
- **Review P3-9:** `active/` is read only when it is a real folder (`lstat`), so a symlinked `active` is not followed.
- **Review P3-11:** tests added for unicode names, a regular file and an empty folder named `_to_delete`, a permission
  error (subfolder and top), a vanished file and entry, R2 on a dotfile, exactly-at-cap and nested cap, age rounding and
  the future-mtime clamp, `show_workspace` and `build_report` surviving a raising scan, and a click on a broken path.
- **Secure P3-1:** `_read_doc` uses `os.open(O_RDONLY | O_NOFOLLOW | O_NONBLOCK)`, `fstat` + `S_ISREG`, then `fdopen`
  (a swapped FIFO cannot block, a swapped link is not followed); `_measure` does `lstat` itself and returns the
  not-measured result when the top is not a real folder.
- **Secure P3-2:** no `os.stat` through a link any more. `_link_state` follows a link by hand, one `lstat` per component,
  and only through paths under the lab or `HOME` (or above them, to reach them); a link that leads anywhere else, directly
  or after an in-lab hop, is "unchecked": a `NOTE` row "not checked" (only when no other row lists that path), never R6.
  Loops and chains over 40 hops are broken, as the OS would say.
- **Secure P3-4:** the `_maybe_weekly_scan` docstring now says the report holds file and folder names, symlink targets and
  absolute paths; this spec (Proposal) and the README say so too.
- **Secure P3-5:** `main.py` `_visible_text` replaces Unicode categories Cc and Cf characters with `\uXXXX` (`\UXXXXXXXX`
  above the BMP) in every table cell and in the tooltip.
- **README:** "never follows a symlink" now describes the by-hand `lstat` walk limited to the lab and `HOME`.

Changes to existing tests (each follows a documented behaviour change; none weakened): `test_finding_fields` (the new
`partial` key); `test_opens_nothing_for_writing_...` (docs are now opened with `os.open` and `fdopen`, so the open spy sees
a descriptor and the `os.open` paths name the files; it now also asserts `O_NOFOLLOW | O_NONBLOCK`);
`test_readme_symlink_out_of_the_lab_is_not_read` (the unread doc is now one `NOTE` row, not an R1 row for the name it
would have honoured); `test_broken_link_is_listed_with_its_target_and_not_followed` (HOME is set above the fixture, because a
target outside the lab and `HOME` is now "not checked", not R6); `test_lab_root_table_is_report_only_with_show_in_finder`
(the clicked path now exists, because a vanished path opens its parent).

#### Deferred (not done; kept so they are not lost)
- **Secure P3-8:** a hard bound on the walk with `os.scandir` and a counter (`os.walk` lists a whole directory before the
  cap counts it; `_entries` for the root and `active/` is not capped; `_to_delete` is measured twice).
- **Review P3-10:** UI: row height set before layout (the Why column may clip), `run_cmd` still runs on the GUI thread
  (now at most 10 s), and the table is a snapshot, not refreshed.
- Moving `run_cmd` (Show in Finder) to a worker thread or `QDesktopServices` (the rest of secure P3-6).
- Also still open: a lab with more than 50,000 entries, links to iCloud or network volumes, and the real Mac checks listed
  under Not verified below.

## Verify (2026-11-20, same session as the build: not an independent QA pass)

Suite: before the change 260 tests (259 passed, 1 skipped: `test_appkit_guard`); after 290 (289 passed, 1 skipped),
0 failures. The pytest process still crashes at interpreter exit (exit 134 or 139) after all tests pass, which is the
open TODO item from 2026-11-20 and is not new; counts come from `--junitxml`.

Mutation check by hand (`scratchpad/mutate.py`, each mutant applied alone, the suite run, then reverted): 40 mutants,
40 killed, 0 survived.

| Mutant | Killed by |
|---|---|
| R1 condition flipped; dotfile allowance removed; always-OK names removed | clean lab, dotfile, one-per-rule tests |
| R1 empty-folder skip or broken-link skip removed (double reports) | `test_r1_does_not_double_report...`, one-per-rule |
| R2 condition flipped; a symlink counted as a file | clean lab; out-of-lab symlink test |
| R3 condition flipped; R3 age taken from the newest file | clean lab; `test_r3_absent_and_present` |
| R4 condition flipped; `active/` exclusion or disposable-name exclusion removed | clean lab, R4 scope test |
| R5 condition flipped; dot-entry skip removed; a broken link also reported as a project | clean lab, R5 tests, R6 test |
| R6 condition flipped; `active/` not scanned; root not scanned | R6 tests |
| each of R1 to R6 removed (rule's report call replaced by a no-op) | one-per-rule |
| symlink check made to follow links: `is_dir`, `is_file`, `os.walk(followlinks=True)`, `lstat` to `stat`, `is_symlink` always False, a doc read through a symlink | out-of-lab symlink tests, README-symlink test |
| walk cap removed | `test_walk_cap_makes_size_unknown` |
| scan writes a file; `os.open` for writing; runs a subprocess; opens a socket | `test_opens_nothing_for_writing_runs_no_subprocess_no_network` (tree before and after, `open`/`os.open` spies, patched `subprocess`, `socket`) |
| report: `lab_root` key removed | `test_report_has_a_lab_root_list...` |
| dialog: lab root not scanned; Show in Finder without `-R`; cells made checkable; table not shown | the three new dialog tests |

Real read-only run against `/Users/as/Documents/lab` (`lab_root_checks.scan`, then the old script's
`python3 -c "import folder_audit as f; [print(i['title']) for i in f.run_audit()['findings'] if i['status']!='good']"`,
same day, nothing written or moved; `--serve` and the fixers not run):

| | R1 | other |
|---|---|---|
| `lab_root_checks` | `build_marker.py` (15 KB), `runners` (861 MB), `setup_github.command` (4 KB) | R6: `lab_dashboard_data.json` and `lab_projects_monitor_page.html` (root symlinks to `dashboards/...` targets that do not exist) |
| `folder_audit` | `build_marker.py`, `runners`, `setup_github.command` | none |

R1 matches exactly. The two R6 rows are the root-symlink coverage that the Define added and Folder Audit never had;
both targets are missing in `dashboards/` today (checked with `ls`), so they are real findings, not false ones.
The `show_tracker` root symlink resolves and is named in the docs, so it is not reported.

Not verified: the window itself (no screenshot; the table is covered offscreen by tests only), Show in Finder on the
real Mac (`open -R` is asserted as the command, not run), the weekly scan firing in the installed app, a lab with more
than 50,000 entries under one root folder (covered with a patched cap only), a symlink to an iCloud or network
volume (`os.stat` on the link was not tried against one). No independent review, QA or Secure pass has run.

### Verify: fix pass (2026-11-20, same author as the fix: not an independent QA pass)

Suite: before the fix pass 290 tests (289 passed, 1 skipped); after 332 (331 passed, 1 skipped: `test_appkit_guard`), 0
failures, counts from `--junitxml`; the process still exits 139 at interpreter exit after all tests pass (the known open
crash). New: 33 in `test_lab_root_checks.py`, 8 in `test_workspace_dialog.py`, 1 in `test_workspace_extra.py` (42 more than 290).

Mutation check by hand (`scratchpad/mutate2.py`, each mutant applied alone against `test_lab_root_checks.py`,
`test_workspace_dialog.py`, `test_workspace_extra.py`, then reverted): 55 mutants, 55 killed. The first run left three
alive: two were wrong patterns in the script (not applied) and re-ran killed; one, `_read_doc` treating a dangling link as
missing, survived because macOS answers `O_NOFOLLOW` on a link with ELOOP, so
`test_read_doc_a_dangling_link_is_not_read_even_where_open_reports_not_found` was added (forces `FileNotFoundError`) and kills it.

| Behaviour | Mutants killed |
|---|---|
| NFC (P3-3) | R1 name, R5 name, doc text not normalised |
| R3/R4 (P3-2) | R4 keeps `_to_delete`; R3 reports a broken link; R3 file wording used for a link |
| doc reads (secure P3-1) | no `O_NOFOLLOW`; no `O_NONBLOCK` (FIFO blocks the test); no `S_ISREG`; dangling link counted as missing; fd leaked on a non-file |
| unread doc (P3-4) | R1 or R5 still run; no NOTE row |
| `_measure` (P3-6, secure P3-1/P3-3) | top not `lstat`ed; no `onerror`; vanished file not partial; cap not partial; unreadable top kept as 0 B; `partial` always False; cap `>` to `>=` |
| vanished, R5, active (P3-7/8/9) | vanished entry 0/0; R5 measured; symlinked `active` followed |
| links (secure P3-2) | everything allowed; ancestors not allowed; unchecked counted as broken; hop limit 1000; `..` ignored; absolute target not reset; a hop through a link not followed; no NOTE for unchecked; NOTE even when already listed |
| R3 text, ages, report | capped R3 shows count and age; partial R3 not "at least"; age not clamped; age rounded; `partial` key dropped; NOTE sort |
| `scan_safe` (P3-5) | no catch; `show_workspace` uses `scan`; `build_report` uses `scan` |
| `main.py` (P2-1, secure P3-5/6) | Cf not replaced; Cc not replaced; astral form; symlink not special; vanished not special; always `-R`; timeout 60; failure ignored; success keeps "Failed"; partial size and unknown age not labelled; text and tooltip not sanitised |

Not verified (fix pass): the window on screen; `open <parent>` and `open -R` on the real Mac (asserted as the command, not
run); the weekly scan in the installed app; a link to a real iCloud or network volume (the new code never stats one);
whether macOS Finder reveals a symlink's target for `open -R` (the reason for the parent rule is the security review's
note, which itself was not verified); a real swap race (primitives only); a lab over 50,000 entries. No real-lab run was
made in this pass. No independent QA or re-review of the fix pass has run.
