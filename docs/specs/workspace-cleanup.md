# Spec: workspace cleanup beyond `lab/active` (worktrees, archive, backups, root)

Status: **Define approved by the owner 2026-11-17 for slice 1** ("Approve slice 1": fix 4.1 plus the
Worktrees section; recorded in `approvals.jsonl`). **4.1 is built** (section 9). The Worktrees card
waits at the **Architect gate** (section 10); archive, backups and caches stay proposals. Written 2026-11-17 from a read-only review; no file was changed or
deleted while measuring. Tier `public`; Foundry phase: **Define** (Design/Architect sections are
proposals inside this file). Not one of the in-flight specs (`secrets-vault`, `sidebar-redesign`).

## 1. What the app cleans today

| What | Where | Rule | Confirmation | Evidence |
|---|---|---|---|---|
| Caches `__pycache__ .pytest_cache .mypy_cache .ruff_cache .cache` | each `lab/active/<project>/` (any depth) | always offered, **permanent delete** (`shutil.rmtree`) | tick box (nothing pre-ticked; "Select all safe" ticks caches only) + a confirm dialog listing them | `lab_health.py:216`, `main.py:3626-3628`, `main.py:3604-3606` |
| Envs `.venv venv env node_modules build dist` | same | needs lockfile/manifest; nothing running from it; `.venv`/`node_modules` unused 7 days (`ENV_IDLE_DAYS`), `build`/`dist` project idle 30 days; git-ignored only; **moves to Trash** after a rebuild record is written | per-env tick + confirm dialog with last use and rebuild cost; "no record, no trash" | `lab_health.py:217-285,730-778`, `main.py:3607-3640` |
| Guards | | linked/out-of-tree projects (`altmerch_store`, `syndustryx`) never cleaned; every path must resolve inside its project; symlinks skipped | | `lab_health.py:1044-1070` |
| System caches | `~/Library/Caches`, `~/.cache`, `~/.npm`, Xcode DerivedData... | each tool's own cleanup (`pip cache purge`, `uv cache clean`, `brew cleanup --prune=all`) or empties the folder; Docker report-only; refuses paths outside `$HOME` | ticks + confirm | `lab_health.py:1156-1235` |
| Backup deletions on Drive | `Backups/MacBook/_deleted/<date>/` | with `MIRROR=1`, rsync `--delete --backup` archives removals; **no retention or pruning anywhere**. README: "Prune those dated folders occasionally" | Mirror mode is opt-in; "Preview deletions" button | `_Admin/backup/backup_to_gdrive.sh:67-74,138,168`, `README.md:333-336` |

The scan only iterates `lab/active/*` (`main.py:1329-1333`). Everything is manual (one button,
one confirm), there is no schedule, no report of what is left, and no age or retention rule outside
`lab/active`.

## 2. Gaps (measured 2026-11-17, read-only; free disk 324 GB, 64% used, so the driver is order, not space)

**G1. Worktrees are invisible to the app, and where it does see them it is unsafe.**
- Agent worktrees: 22 in `active/*/.claude/worktrees/` (lab_hub 4, provisio 1, sentinel 1, sonar 10,
  syndustryx 6) plus 3 in the lab root `.claude/worktrees/` plus `worktrees/imprint-harden-ship`
  (395 MB). About **1.9 GB** in all. Nothing in the app reports or cleans them.
- **Safety bug (confirmed):** `_find_disposable` runs `find <project>` with no exclusion of
  `.claude/` (`main.py:1426-1437`), and `.claude/worktrees/` is git-ignored via
  `.git/info/exclude`, so a worktree's `node_modules`, `dist`, `build`, caches are listed as that
  project's own. Verified: `git check-ignore` says ignored for
  `provisio/.claude/worktrees/local-ci-f12827/node_modules` (**966 MB**) and
  `lab_health.rebuild_command` returns `npm ci` for it, so after 7 days unused it is offered, and
  Clean would trash an env inside another agent's worktree. This contradicts the lab rule "never
  silently clean another agent's worktree" (lab `AGENTS.md`, Hard rules). The same walk deletes
  `__pycache__` inside worktrees permanently. (`_EVIDENCE_SKIP` in `lab_health.py:517` already
  excludes `.claude` for last-use evidence, so the scan is inconsistent with itself.)

  | Worktree (state at review) | MB | last commit | clean | merged into base | verdict |
  |---|---|---|---|---|---|
  | provisio `local-ci-f12827` | 975 | 4 d | yes | yes | candidate, report |
  | sonar `cool-leavitt-1b6b6d` | 218 | 29 d | yes | yes | candidate |
  | imprint `worktrees/imprint-harden-ship` | 395 | 26 d | yes | yes, branch pushed | candidate |
  | sonar `brave-elbakyan`, `censoring-pr2`, `heuristic-panini`, `followurl` | 4-5 each | 35-36 d | yes | yes | candidate |
  | sentinel `macaddr-lows` | 8 | 17 d | yes | yes | candidate |
  | syndustryx `a8-gaps` (pushed), `a8-ux-fixes` | 28, 27 | 4 d | yes | yes | candidate after N days |
  | lab root `festive-lamport`, `keen-bun`, `kind-golick` | 0.5 each | 34-35 d | yes | yes | candidate |
  | lab_hub `zealous-benz` | 5 | 0 d | **13 dirty** | yes | never (uncommitted work) |
  | syndustryx `policy-none-rootcause` | 28 | 4 d | **1 dirty** | yes | never |
  | sonar `agent-a38c53e0d770da7c1` | 5 | 0 d | yes | **1 commit ahead** | never (unmerged) |
  | 5 more with last commit today (lab_hub x3, sonar `release-2296`, syndustryx `phase3`, `phase4`, `a1-ops`) | 3-69 | 0 d | yes | yes | too fresh; may be live |

  "Merged" = HEAD is an ancestor of the repo's current branch (local ref, no fetch). Sum of the
  clean, merged, not-fresh rows: about 640 MB at 14+ days, about 1.7 GB at 3+ days.

**G2. `archive/` (1.1 GB, lab root, git-ignored) is never looked at.** `archive/fixes_2026-10-12`
is 1.1 GB: 7 checkouts that are also **registered git worktrees** of imprint, provisio and sentinel
(`git worktree list`). 6 of 7 are clean and merged into `origin/main`/`main`; **`sentinel` is not
merged** (branch `fixes/audit-tier1-2026-10-12`, 25 MB, no upstream). `provisio-deps` alone is 973 MB
(`node_modules`). None has an upstream, so "merged" rests on the ancestor check only. Deleting these
with `rm` would leave dangling worktree entries in three repos; they need `git worktree remove`.
`autopilot-2026-11-17` (8 MB) is a same-day fold-in archive. The five `*_2026-09-30` folders total
under 1 MB.

**G3. `backups/` (332 MB) has no age rule.** Lab `AGENTS.md`: "ignored snapshots; delete once
nothing needs them." 7 snapshots, dated by mtime: 5 are 36-54 days old (305 MB: `pre_headroom_merge`
117 MB, `sonar-app-prev.noindex` 98 MB, `pre_backstage_split` 45 MB, `pre_identity_rewrite` x2
44 MB). Mentioned only in history docs, except `pre_identity_rewrite_20261009` (25 MB), which no
doc mentions at all. `sonar-data` (today) and `agents_md_pre_consolidation` (5 d) are recent.
`sonar-app-prev` and `sonar-data` are named in sonar's audit and spec docs, so "unreferenced" must
be a real check, not a glob.

**G4. Drive `_deleted/<date>/` grows forever** once Mirror mode is on (last row of the table in
section 1; `backup_to_gdrive.sh` has no pruning). Not
measured: the Drive copy is not read here (a `du` on the CloudStorage mount can trigger downloads).

**G5. Venvs are the biggest item and are already handled, but unevenly.** About 15 GB of `.venv`
over 9 projects (backup_manager 1.3 GB, imprint 1.5, imprint-base 1.5, imprint-deps 1.5, lab_hub 1.4,
git_autosync 1.2, backstage 1.2, sonar 1.2, provisio 1.2, **sentinel 2.8**) plus provisio
`node_modules` 0.97 GB. Lab Health already offers them at 7 idle days. Not re-measured for idleness
here. Gap: `imprint`, `imprint-base`, `imprint-deps` are one repo with three 1.5 GB venvs (worktrees),
and the duplicate marker only compares lockfile hashes, not worktree siblings.

**G6. Root loose items** (`folder_audit.py` finds these, see section 3): `Career Roadmap.zip` 1.7 MB,
`build_marker.py`, `setup_github.command`, `runners/` **875 MB** (`runners/syndustryx-ci`, purpose
unknown), `__pycache__/` 132 KB in the root.

**G7. `__pycache__` is noise, not space:** about 21 MB across all projects (syndustryx 13.6 MB,
sentinel 3.9 MB, rest under 1 MB) and 132 KB in the lab root, which is outside `lab/active` so the
app never sees it. Cheap and safe; low value.

**G8. `~/Documents` outside `lab`** (all read-only du): `lab` 33.4 GB, `Files` 1.6 GB, `Business`
1.4 GB, `Personal` 381 MB, `College Projects` 324 MB, `Misc` 226 MB, `KawaiiGPT` 107 MB, `Codex`
51 MB. The app cannot judge these (no git, no manifest, personal data). Report only.

## 3. Overlap with `folder_audit.py` (lab root)

`folder_audit.py` is structural and name-based; it never measures size, age of contents or git
state inside a folder.

| Concern | `folder_audit.py` (`lab/folder_audit.py`) | Backup Control Center |
|---|---|---|
| Unknown root files/folders (`Career Roadmap.zip`, `runners/`...) | flags by name vs AGENTS/README mentions (`:174`), fix = move to `_to_delete/` | no |
| `.bak/.orig/patch_*.py` stale files, `_to_delete/` pending, empty root dirs, missing `.gitignore`, non-Foundry repos, AGENTS.md over 150 lines | yes (`:206-410`), fixers `:524` | no |
| Contents of `archive/`, `backups/`, `worktrees/` | **no**: these names are "known", so they are never opened | no (today) |
| Per-project reclaimable sizes | summary only (`usage`, run_audit) | yes, with ticks |
| Caches and envs inside `active/*` | no | yes |
| Agent worktrees | no (`.claude` is `ALWAYS_OK`) | scanned by accident, see G1 |

Proposed split to avoid overlap: **`folder_audit.py` keeps what is at the lab root by name;
Backup Control Center takes everything measured by size, age and git state** (worktrees, `archive/`,
`backups/`, caches wherever they live). The app does not re-flag `Career Roadmap.zip` and friends;
it may show a line "N root items flagged by folder_audit" read from its report (optional, Phase 2).

## 4. Proposal

### 4.1 Fix first (bug, own commit, no new UI): keep Lab Health out of other agents' worktrees
`_find_disposable` skips `.claude/` and any directory whose `.git` is a file (a linked worktree)
unless it is the project root. Test: a fixture with `.claude/worktrees/x/node_modules` is never
returned by `cleanup_targets`. This is a hard-rule fix, independent of the rest, and can ship before
the gate on the new features. (Owner decides whether to fast-track it.)

### 4.2 New card: **Workspace** (beside Lab Health), report first, delete second
Read-only table by default: Item, Where, Size, Age, State, Verdict (offered / kept / never) and why.
Four sections: **Worktrees**, **Archive**, **Backups**, **Caches outside active**. A "Scan" button
and a summary line in the Overview ("N MB reclaimable, M items waiting for you").

### 4.3 Rules (each item must pass **all** its gates; failing one gives a visible reason, never silent)

**Worktrees** (agent `.claude/worktrees/*`, lab root `worktrees/*`, lab root `.claude/worktrees/*`):
1. `git status --porcelain` empty (no dirty, no untracked files other than ignored build output).
2. HEAD is an ancestor of the repo's default branch, **or** its branch exists on a remote at the same
   commit. A branch with commits not on any other ref is never offered.
3. Newest mtime of any tracked file and last commit both older than **14 days** (setting, default 14).
   Anything touched today is treated as live. No process has its cwd inside (`lsof`, as the env check
   already does in `lab_health.env_users`).
4. Removal is `git worktree remove <path>` (never `rm -rf`), which itself refuses a dirty tree; the
   branch ref is **kept** (it is merged or pushed anyway, and costs nothing). The path goes to the
   Trash first only if `git worktree remove` is not usable (locked); otherwise left in place.
5. A rebuild record is not needed: a worktree is recreated from its branch/commit; the record stores
   repo, path, branch and HEAD so "Restore worktree" is `git worktree add`.
The owner's lab rule stays: a worktree failing any gate is reported with its path and left intact.

**Archive** (`archive/*`): offered only when the folder is a set of checkouts whose every git member
passes the worktree gates (merged, clean, **and** no unmerged branch); an unmerged member
(`archive/fixes_2026-10-12/sentinel`) blocks only itself. Plain non-git archive folders are
age-listed and never offered for deletion (manual). Removal of registered worktrees uses
`git worktree remove`; then the empty parent is left for the owner.

**Backups** (`backups/*`): offered when the snapshot is older than **30 days** (setting) **and** no
file in `AGENTS.md`, `README.md`, `docs/`, or a project's `TODO.md`/`docs/` names it in a
non-history file (history docs `docs/history/**` and `lab-notes-*` do not count as a reference; they
are listed in the tooltip so the owner can judge). Always **Trash**, never `rmtree`.

**Caches** (`__pycache__` etc.): the same rule as today, extended to the lab root and `scripts`-style
folders outside `active/`; still skipping `.claude` and worktrees. Permanent delete stays, since they
regenerate.

**Venvs**: unchanged (7 days, Lab Health). Addition: for projects that are worktrees of one repo
(`imprint`, `imprint-base`, `imprint-deps`) show the three venvs as duplicates and mark the
least recently used (reuse of the existing duplicate marker).

**Drive `_deleted/`**: a **report-only** line (count of dated folders and total age, read from
`rclone`/the mount only if the owner enables it) and a suggested prune command. No automatic prune
in this spec (see section 6).

### 4.4 Confirmation and reporting to the owner
- **Nothing is ticked by default and nothing runs on a schedule that deletes.** Same pattern as Lab
  Health: tick, confirm dialog listing path, size, age, state and why it passed, then act.
- Optional **weekly scan** (the app's own launchd cadence): scans and updates the report and the
  Overview line only. It never deletes.
- Report written to `~/Library/Application Support/Backup Control Center/workspace_report.json` and
  one dated line in the app log per action (what, path, size, how it can be undone). No secrets, no
  file contents.
- Every action is reversible where possible: Trash for folders, branch refs kept, rebuild/restore
  record written first ("no record, no trash" as today).

## 5. Stays manual (the app reports, the owner or an agent decides)
- Anything dirty, unmerged, or touched in the last 14 days; another agent's live worktree.
- `lab` root loose files and `runners/` (folder_audit's finding; `runners/syndustryx-ci` 875 MB
  needs the owner to say what it is).
- `~/Documents/{Files,Business,Personal,College Projects,Misc,KawaiiGPT,Codex}`: no project
  structure; report only.
- Docker, simulators and model caches (already unticked or report-only).
- Drive `_deleted/` pruning, until a retention period is decided.
- Anything under `docs/legal`, `docs/foundry/*.jsonl`, `.env`, Keychain items: never listed.

## 6. Decisions for the owner
1. **Fast-track the 4.1 fix** (stop Lab Health listing agent worktrees) ahead of the feature? Recommended yes.
2. Worktree age threshold: 14 days (recommended), or 7 / 30?
3. Backup snapshot age: 30 days (recommended)? Should an unreferenced snapshot (`pre_identity_rewrite_20261009`) be offered earlier?
4. `archive/fixes_2026-10-12`: confirm the app may offer the six merged checkouts (about 1.09 GB) via `git worktree remove`, and that `sentinel` (unmerged, 25 MB) stays manual until you decide.
5. Drive `_deleted/` retention: a number of days (for example 90) now, or leave manual?
6. Weekly report-only scan on, or button only?
7. Scope: build everything (4.1-4.4), or 4.1 plus the Worktrees section only as the first slice (recommended; the other sections follow once that has run safely for a few weeks).

## 7. Success measure (for Verify)
- Unit tests (Qt-free, in `lab_health.py` style) for each gate with fixtures: dirty tree, unmerged
  commit, fresh mtime, live cwd, symlink, path outside root, referenced backup. Mutation-check each
  gate (removing it must fail a test).
- A dry-run on the real workspace lists exactly the verdicts in the G1 table (same rows offered,
  `zealous-benz`, `policy-none`, `agent-a38c53e0d770da7c1` and `sentinel` in `archive/` never offered).
- Evidence of reclaimable space shown before and after on one real item, with the Trash entry.

## 8. Risks and notes
- "Merged" uses local refs without a fetch; a stale `origin/main` can under-report merged (safe
  direction) but never over-report, because the check is ancestor-of, not name-based.
- `git worktree remove` on `archive/fixes_*` touches `.git/worktrees` metadata of imprint, provisio
  and sentinel, which are other projects' repos: the app must run it from that repo and only for
  entries under the lab root.
- Foundry: this is a user-visible, data-deleting change, so Architect (state, boundaries) and Secure
  (file writes, untrusted paths) are required; legal: tier `public`, no new personal data (no change
  to the privacy note expected). Not checked: whether the 8 unfilled `app-context.md` placeholders
  affect this spec (the session-start hook warned of them).
- Evidence limits: sizes from `du -sk` on 2026-11-17 22:xx; ages are last-commit ages and directory
  mtimes; venv idleness and the Drive `_deleted/` size were **not** measured.

## 9. Build log: slice 1, part A (2026-11-17)
4.1 fix built: `lab_health.in_foreign_tree()` (`.claude/` component or a linked worktree, told apart
from a submodule by `.git` -> `/worktrees/`) filters `_find_disposable` (`main.py`) and, as a second
guard, `cleanup_targets`. Tests: `test_in_foreign_tree_flags_claude_dir_and_linked_worktrees`,
`test_cleanup_targets_never_return_worktree_contents`; mutation-checked (function forced to `False`
fails both). Full suite: 164 passed. Real paths: `provisio/.claude/worktrees/local-ci-f12827/node_modules`
now `True` (skipped), `provisio/node_modules` `False`. Not done: independent review, CHANGELOG/TODO
entry, version bump, install. Uncommitted.

## 10. Proposed Architect: Worktrees card (needs the Architect gate: new state and a boundary)
- **Module:** new Qt-free `workspace.py` (like `lab_health.py`): `scan_worktrees(lab_root) -> list[dict]`
  and `remove_worktree(item)`. The card in `main.py` only renders rows and calls these.
- **Discovery:** `git worktree list --porcelain` from each `active/*` repo (and the lab root),
  de-duplicated by path; scope limited to paths under the lab root. Read-only, `timeout` on every git call.
- **Verdict per row** (gates from 4.3): clean, ancestor of the default branch or same commit on a
  remote, newest mtime and last commit older than N days (default 14), no process cwd inside.
  Every gate result is stored on the row so the UI shows why a row is kept.
- **Removal:** `git -C <owning repo> worktree remove <path>` (no `--force`); the branch ref stays.
  Before removal write `worktree_records/<id>.json` (repo, path, branch, HEAD) beside `env_records/`;
  no record, no removal. The paths are re-verified at click time (state may have changed since the scan).
- **Boundary:** the only write outside this app's own files is `git worktree remove` in other repos,
  for paths under the lab root only; never `--force`, never `rm`, never a branch delete or push.
- **State and threading:** the scan runs in a `QThread` started with `start_thread()` (invariant
  in `app-context.md`); one scan at a time; the result is a list of plain dicts.
- **Open for the owner:** threshold default (14 d), and whether `worktrees/imprint-harden-ship`
  (branch pushed, merged) may be offered like an agent worktree. After this gate: Plan, Build,
  Review (different agent), Verify, Secure (file writes, untrusted paths), Document.

## 11. Build and review log: slice 1 (2026-11-17)
Approvals recorded: Define ("Approve slice 1"), Architect ("Approve Architect").
Built: `workspace.py` (gates, scan, restore record, removal), the **Worktrees** dialog on the Lab
Health card (`main.py`), README/TODO entries. Tests: 184 passed in the full suite; every gate
mutation-checked (forcing each to pass fails a test). Real dry run (read-only, 33 worktrees): offered
`archive/fixes_2026-10-12/provisio-deps` (950 MB) and three 0.5 MB lab-root `.claude/worktrees`;
all the rest kept with a reason. Without the ignored-files gate it would also have offered the sonar
worktrees, whose ignored `sonar/macro` and `sonar/playmaker` are nested repos that
`git worktree remove` would have deleted.
Independent review (code-reviewer agent): P1 findings fixed: allowed-name ignored dirs holding the
only copy (now need a manifest, and no nested repo in build/dist/.cache); the `lsof` gate failing
open (now blocks); a linked worktree named like a cache (`dist`) still cleaned by Lab Health (now
checked on the target itself). P2 fixed: failed `git status --ignored` now blocks; every gate is
re-run right before the removal; "merged" now means the default branch (origin/HEAD, else
main/master). P3 fixed: restore-record names no longer collide, restore command is shell-quoted.
Known limits: only a process's working directory is checked, not its open files; `git worktree remove`
ignores git-ignored caches, so those are deleted with the worktree; the 14-day threshold is a constant
(not yet a setting); not installed or released; no Secure-phase pass yet.

## 12. Secure log: slice 1 (2026-11-18)
Independent security-engineer review: no P0/P1; removal fails closed; all subprocess calls are list
args, no shell, with timeouts. Fixed: P2 `worktree list` now uses `-z` (a newline in a folder name
could forge another entry); P2 git runs with `--no-optional-locks`, `core.fsmonitor=false`,
`core.hooksPath=/dev/null` in `workspace.py` (a repo-local fsmonitor ran a command in scratch);
P2 dialog labels and the confirm box are plain text (branch/folder names are other agents' input);
P3 restore records are mode 600 in a 700 folder; `--` before the path in `git worktree remove`.
Tests: 188 passed; each new fix mutation-checked; real dry run unchanged (same four offered).
Accepted, not fixed: (a) a new ignored file created in the seconds between the final re-check and the
removal is deleted (git refuses dirty/locked trees; needs same-user activity); (b) `lsof` exits 1 when
it cannot see some processes and its output is still used; (c) the symlink-swap race was not
tested; (d) `lab_health.py:62` (existing code) still runs plain `git` on every project and so
inherits repo-local fsmonitor/hooks config: separate, older exposure, proposed as its own fix;
(e) `docs/foundry/app-context.md` Stack/Commands/Security surface are still the unfilled template.

## 13. Verify log: slice 1 (2026-11-18)
Independent qa-engineer pass on commit e77a6f0: suite 188 passed, three repeat runs of the three
touched test files clean, real-workspace dry run as required (same 4 offered; dirty, unmerged and
live ones kept). Verdict FAIL (conditional) on test gaps: 36+7 mutants planted, 17 survived, among them
`--force` on `git worktree remove` (P1), the pushed-but-unmerged path (P1), the age gate boundary and
sources, lsof non-zero exit, symlink/missing/outside-root, `--no-optional-locks`, git refusing the
removal. Added 10 tests for exactly those; all of those mutants are now killed. Suite 196 passed.
Not covered: the dialog's remove flow in `main.py` (display only is tested), two minor
`lab_health.in_foreign_tree` mutants (backslash normalisation, ValueError return), and no real
removal has been run on the lab. The QA agent has not re-run on the new tests.

## 14. Define: slice 2 (Archive, Backups, Caches), 2026-11-18, awaiting the Define gate
Owner answers (2026-11-18): backup age **30 days**; a README tree line or history note does **not**
block a snapshot (listed in the tooltip); an unreferenced snapshot gets **no** earlier rule; Drive
`_deleted/` stays **manual** (report-only line plus a suggested prune command); weekly scan **on,
report-only, never deletes**. Not asked, proposed: worktree age becomes a setting (default 14, range 7-60).

**Re-measured 2026-11-18** (`du -sk`, mtime ages, read-only): `archive/fixes_2026-10-12` 143 MB
(slice 1 removed `provisio-deps`; its restore record exists); of its 4 registered worktrees none is
offered (sentinel unmerged; imprint has ignored `data`; two provisio lack a manifest for `node_modules`).
So Archive adds almost nothing for git members: slice 1 already covers them. `backups/`: 7 snapshots,
332 MB; 5 over 30 days (`pre_backstage_split` 51 d 45 MB, `pre_headroom_merge` 49 d 117 MB,
`pre_identity_rewrite_0924` 55 d 20 MB, `pre_identity_rewrite_1009` 40 d 25 MB, `sonar-app-prev` 37 d
98 MB). Non-history docs naming them: `sonar-app-prev`, `sonar-data` (sonar audit/spec, block);
`pre_identity_rewrite_1009` named nowhere. Lab README tree names three others (does not block).
Root `__pycache__` 188 KB. `runners/` 878 MB, unknown purpose, stays manual. Drive `_deleted/`: not measured.

**Scope of slice 2** (all offered only by tick + confirm; nothing pre-ticked):
1. **Archive:** list every `archive/*` entry with size and age (new: `archive/artifacts` 9.4 MB,
   `autopilot-2026-11-17` 7.9 MB). Git members are shown with their slice-1 verdict (no second removal
   path). Non-git folders are **report-only**, never offered.
2. **Backups:** offered when older than 30 d and no non-history doc (not README tree lines, not
   `docs/history/**`, not `lab-notes-*`) names it, searched in lab `AGENTS.md`, `docs/`, each project's
   `AGENTS.md`, `TODO.md`, `docs/` (a real search, not a glob). Move to the **Trash** (never `rmtree`),
   restore record first ("no record, no trash"). Today's result would be: 4 offered (about 207 MB:
   `pre_backstage_split`, `pre_headroom_merge`, `pre_identity_rewrite` x2), `sonar-app-prev` blocked, rest too young.
3. **Caches outside `active/`:** same cache names as Lab Health, lab root and top-level scratch folders,
   skipping `.claude` and worktrees; permanent delete as today.
4. **Report-only:** Drive `_deleted/` line (only if the owner enables it) and `runners/`/`~/Documents`
   items from section 5; weekly report-only scan writes `workspace_report.json`.
5. Worktree age setting (default 14) wired to slice 1's gate.

Not in scope: `folder_audit.py` duplication, `lab_health.py:62` hardening, readiness-audit findings,
dashboards consolidation. Success measure: section 7 tests per gate, mutation-checked, plus a read-only
real dry run showing the 4 backups offered, `sonar-*` blocked, and one real Trash entry with its record.
Next: Define gate (owner), then Architect gate (new Trash and scan-schedule boundaries), Build, Review, Secure, Verify.

## 15. Proposed Architect: slice 2 (needs the Architect gate: new state, Trash boundary, schedule)
- **Modules (Qt-free, like `workspace.py`):** new `workspace_extra.py` (keeps `workspace.py` focused on
  worktrees): `scan_archive(lab_root)`, `scan_backups(lab_root, min_days, now)`, `backup_references(name, lab_root)`,
  `scan_root_caches(lab_root)`, `build_report(...)`. `main.py` only renders rows and calls them, same as the
  Worktrees dialog. Gates return reasons, never silent; each row stores its gate results.
- **Backups gate:** age (mtime of the newest file inside, not the folder) over `backup_min_days` (default 30)
  and no reference in the searched files (lab `AGENTS.md`, `docs/` minus `docs/history/**` and `lab-notes-*`,
  each project's `AGENTS.md`, `TODO.md`, `docs/`; README excluded per the owner). Search is a plain
  substring read of text files, size-capped, no shell, symlinks skipped. Snapshot must be a real directory
  directly under `backups/` and inside the lab root; a failed search blocks (fail closed).
- **Removal:** `QFile.moveToTrash` (the call Lab Health uses, `main.py:3764`), never `rmtree`. Record first in
  `backup_records/<id>.json` (path, size, age, mode 600 in a 700 folder; restore = "Put Back" from the
  Trash); no record, no trash. Gates are re-run at click time. Qt stays in `main.py`; the module takes the
  mover as a parameter so tests use a fake.
- **Caches outside `active/`:** reuse Lab Health's cache names and `in_foreign_tree`; scope is the lab root and
  its top-level scratch folders only, never `.claude`, `archive`, `backups`, symlinks or other repos' trees.
- **Archive:** read-only; git members take slice 1's verdict via `scan_worktrees` (no second removal path).
- **Weekly scan (no new launchd agent):** the app is already a menu-bar resident, so a single `QTimer` checks
  `last_workspace_scan` in `state.json`; if older than 7 days it runs `build_report` in a `QThread` via
  `start_thread()` (invariant), writes `workspace_report.json` (mode 600) and updates the Overview line.
  Setting `workspace_weekly_scan` (default on), read-only code path, no delete function reachable from it
  (tested: the scan module imports no mover). When the app is not running the scan does not run (accepted).
- **Settings:** `worktree_min_days` (7-60, default 14) and `backup_min_days` (7-120, default 30), clamped;
  stored in `state.json`.
- **Boundary:** writes only to this app's own folder plus Trash moves of `backups/<name>` under the lab root
  and the existing cache deletes. No network, no git writes, no Drive access in this slice.
- **Open for the owner:** none new; the in-app timer instead of a launchd job is the only design choice to confirm.
  After this gate: Plan, Build, Review (different agent), Verify, Secure, Document.

## 16. Build log: slice 2 (2026-11-18)
Approvals recorded: Define slice 2 ("Approve Define"), Architect ("yes"). Built: `workspace_extra.py`
(backup gates, Trash via an injected mover, archive list, root caches, weekly report), the **🗂 Workspace…**
dialog and in-app weekly timer in `main.py`, settings in `state.json`, README/TODO. Tests: 221 passed
(24 new in `test_workspace_extra.py`, 2 in `test_workspace_dialog.py`); gates mutation-checked (age, reference,
size-cap fail-closed, eligibility recheck, record-before-move, symlink, cache-root exclusions, repo skip,
history/lab-notes/self-spec exclusion, clock skew); one mutant (`parent.name != "backups"` in `trash_backup`)
is equivalent because the scan already rejects such paths. Real read-only dry run: offered 3 backups (about
185 MB: `pre_headroom_merge`, `pre_backstage_split`, `pre_identity_rewrite_20261009`); kept
`sonar-app-prev` and `pre_identity_rewrite_20260924` (named in `docs/reorg_suggestions_2026-09-26.md`, a
non-history doc, so it blocks: differs from the Define estimate of 4), `sonar-data`, `agents_md_pre_consolidation`;
caches: root `__pycache__` and `dashboards/__pycache__`. Deviation: the Overview line is a tooltip on the
Workspace button (no Overview widget yet). Not done: independent review, Secure, Verify, install, real Trash run.

## 17. Review and Secure log: slice 2 (2026-11-18)
Independent code-reviewer and security-engineer passes on dd5b9c0 (full reports in the shared notes folder,
`review-slice2.md`, `secure-slice2.md`). No P0. Fixed: **P1** the age gate failed open at the 50,000-entry
walk cap (now "age unknown", kept); **P1** a snapshot copied with `cp -a` kept old mtimes and was offered
(age is now the youngest of newest mtime and the folder's birth/ctime); P2 `clean_caches` re-checks the repo
(`.git`), hidden top folders and symlinked parents; P2 tooltips showed other agents' names as rich text
(now escaped, worktree tooltips too); P2 reference search also reads `.sh .py .toml .json .yml .yaml
.command`; P3 named pipes no longer stall the search, `clamp_days` survives `Infinity`, records and the
report are created mode 600. Each fix has a test; the walk cap, birth, pipe, mode and clamp mutants fail the suite.
Suite: 229 passed. Accepted, not fixed: `trash_backup` re-scans all snapshots per ticked item (slow, not
unsafe); the record stays if the move fails; the weekly-scan guard is per card and `last_workspace_scan`
is written when a scan finishes; no process-cwd or nested-git gate for snapshots (Put Back restores);
"scan deletes nothing" holds by call graph and a rmtree-patched test, not by module split; the Overview
line is a tooltip; slice 1 items (d) and (e) still open. Not done: Verify (QA) pass, install, real Trash run.

## 18. Verify log: slice 2 (2026-11-18)
Independent qa-engineer pass on 26bbb8f (report: `verify-slice2.md` in the shared notes folder). Verdict
**PASS with gaps**, no production bug. Suite green; the two new test files ran 3x without flakes; 78 mutants
planted in a copy: 58 caught, 20 survived. Real read-only dry run: offered exactly `pre_headroom_merge`,
`pre_backstage_split`, `pre_identity_rewrite_20261009`; `sonar-app-prev` and `pre_identity_rewrite_20260924`
kept (named by non-history docs); caches `__pycache__`, `dashboards/__pycache__`; no worktree or Trash action
was run. Gaps closed with 15 new tests (suite now 238 passed): `_maybe_weekly_scan` (switch, interval, saves
the time, deletes nothing), the dialog's Clean button (only ticked items, Cancel default, Cancel does nothing,
age setting reaches the click-time re-check, kept backup has no box), the real `_birth`, the 120-day clamp,
`active/` caches refused, record never overwrites, report totals, backup sort order. Re-run survivors on
`main.py`/`workspace_extra.py`: weekly switch, interval, last-scan save, default button, `min_days=0`,
ignore-ticks, kept-backup-gets-a-box, birth, cache-root and record-overwrite mutants are now all killed.
Still untested: branch coverage (no `pytest-cov` in the venv), the real `QFile.moveToTrash` and a real Trash
entry, the in-app QTimer firing, two weekly scans overlapping. Not done: install, release, merge.
Release needs a fresh `legal_gate.py check`: run from this worktree it says "no legal pack: docs/legal/register.md
is missing" (docs/legal is git-ignored and lives only in the main checkout); it must be run there. In the main checkout it says "clear" today (before this branch is merged); it must be re-run after the merge.

## 19. Slice 1 leftovers closed (2026-11-18)
(d) `lab_health.py` `_git` and the `commit_warnings` status call now run git with `--no-optional-locks`,
`core.fsmonitor=false` and `core.hooksPath=/dev/null`, as `workspace.py` does. Side effect: "Commit all" in
Lab Health no longer runs a project's own pre-commit hook (gitleaks still runs). Two tests plant a repo-local
fsmonitor script and a pre-commit hook; both mutants (flags removed from `_git`, from the status call) fail
them. (e) `docs/foundry/app-context.md` placeholders filled from code, README, TODO and tests (Invariants
untouched; its own template line stays). No CHANGELOG file exists; the note lives here and in `TODO.md`.

## 20. Release log (slice 2)

2026-11-18: v2.119 merged (`16097f5`), built and installed. Real-removal check by the owner in the installed app:
`backups/pre_backstage_split_20260927-232944` ticked in 🗂 Workspace… and cleaned. The dialog said "moved to the Trash
(Put Back to restore)"; the folder is gone from `lab/backups/` (6 left) and a mode-600 record
`backup_records/pre_backstage_split_20260927-232944__1795038624.json` was written first. This closes the
"real `QFile.moveToTrash`" gap listed in section 18. Still not verified: the QTimer firing in the live app.
