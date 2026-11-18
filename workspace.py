"""Workspace cleanup rules, no Qt: which git worktrees under the lab root are safe to remove.

A worktree is offered only when every gate passes (see docs/specs/workspace-cleanup.md):
clean, merged into its repo's branch or pushed, untouched for MIN_AGE_DAYS, nothing running
inside it, not a project folder, not locked. Removal is `git worktree remove` (never
`--force`, never `rm`), after a restore record is written; the branch ref is kept.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path

import lab_health

MIN_AGE_DAYS = 14
_STAT_CAP = 20000   # tracked files looked at for "newest edit"
# Git-ignored paths that `git worktree remove` deletes without --force. Only these
# regenerate; any other ignored file (.env, a local database, notes) may be the only copy.
_CACHES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".DS_Store",
           ".ipynb_checkpoints", ".coverage", "htmlcov", ".next", ".wrangler", ".turbo",
           ".vite", "dist.noindex", "build.noindex", "next-env.d.ts", "tsconfig.tsbuildinfo",
           "_build_info.json"}
# Folders that regenerate only when a lockfile or manifest says how (same rule as Lab Health).
_NEEDS_MANIFEST = {".venv", "venv", "env", "node_modules", "build", "dist", ".cache"}
_PACKAGE_DIRS = {".venv", "venv", "env", "node_modules"}   # vendored .git inside is normal
_WALK_CAP = 20000
_AUTO = object()   # "look up the running processes yourself"


# Repos here were written by other agents: never run their fsmonitor or hooks, and do not let
# `git status` refresh the index (a write) inside repos this app does not own.
_SAFE_GIT = ("--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null")


def _git(repo: Path | str, *args: str, runner=subprocess.run, timeout: int = 30):
    try:
        r = runner(["git", *_SAFE_GIT, "-C", str(repo), *args], capture_output=True,
                   text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return r.returncode, r.stdout


def _under(path: str | Path, root: str | Path) -> bool:
    p, r = os.path.realpath(path), os.path.realpath(root)
    return p == r or p.startswith(r.rstrip("/") + "/")


def parse_worktrees(porcelain: str) -> list[dict]:
    """`git worktree list --porcelain` blocks -> dicts. The first block is the main one."""
    out, cur = [], {}
    # `-z` output is NUL-separated, so a newline inside a path cannot forge a field.
    fields = porcelain.split("\0") if "\0" in porcelain else porcelain.splitlines()
    for line in fields + [""]:
        if not line.strip():
            if cur:
                out.append(cur)
            cur = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            cur["path"] = val
        elif key == "HEAD":
            cur["head"] = val
        elif key == "branch":
            cur["branch"] = val.removeprefix("refs/heads/")
        elif key == "detached":
            cur["branch"] = ""
        elif key in ("locked", "prunable"):
            cur[key] = val or True
    return out


def repo_roots(lab_root: Path) -> list[Path]:
    """The lab root and every real (non-symlinked) git repo directly under active/."""
    roots = []
    if (lab_root / ".git").is_dir():
        roots.append(lab_root)
    active = lab_root / "active"
    if active.is_dir():
        for p in sorted(active.iterdir()):
            if p.is_dir() and not p.is_symlink() and (p / ".git").is_dir():
                roots.append(p)
    return roots


def list_worktrees(lab_root: Path, runner=subprocess.run) -> list[dict]:
    """Every linked worktree under the lab root, once, with the repo that owns it."""
    found: dict[str, dict] = {}
    for repo in repo_roots(lab_root):
        rc, out = _git(repo, "worktree", "list", "--porcelain", "-z", runner=runner)
        if rc != 0:
            continue
        blocks = parse_worktrees(out)
        if not blocks:
            continue
        main = blocks[0]["path"]
        for b in blocks[1:]:
            key = os.path.realpath(b["path"])
            if key in found or not _under(b["path"], lab_root):
                continue
            found[key] = {**b, "repo": main}
    return list(found.values())


def cwd_snapshot() -> list[str] | None:
    """Working directories of every running process (lsof), or None when lsof failed.
    A worktree with a process inside it is in use; when we cannot tell, nothing is offered.
    Only the working directory is checked, not every open file."""
    try:
        r = subprocess.run(["lsof", "-n", "-w", "-d", "cwd", "-Fn"], capture_output=True,
                           text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0 and not r.stdout:
        return None
    return [ln[1:] for ln in r.stdout.splitlines() if ln.startswith("n")]


def _newest_edit(wt: Path, runner) -> float:
    """Newest of: last commit time and the mtime of any tracked file."""
    newest = 0.0
    rc, out = _git(wt, "log", "-1", "--format=%ct", runner=runner)
    if rc == 0 and out.strip().isdigit():
        newest = float(out.strip())
    rc, out = _git(wt, "ls-files", "-z", runner=runner, timeout=60)
    if rc == 0:
        for i, rel in enumerate(out.split("\0")):
            if i >= _STAT_CAP:
                break
            if rel:
                try:
                    newest = max(newest, os.lstat(wt / rel).st_mtime)
                except OSError:
                    pass
    return newest


def _has_nested_git(folder: Path) -> bool:
    """True when `folder` holds a nested git repo, or is too big to look through."""
    seen = 0
    for _dirpath, dirs, files in os.walk(folder):
        seen += len(dirs) + len(files)
        if ".git" in dirs or ".git" in files or seen > _WALK_CAP:
            return True
    return False


def default_branch(repo: Path, runner=subprocess.run) -> str:
    """The repo's default branch: origin/HEAD, else main/master, else the checked-out one."""
    rc, out = _git(repo, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD", runner=runner)
    if rc == 0 and out.strip():
        return out.strip().removeprefix("origin/")
    for name in ("main", "master"):
        rc, _ = _git(repo, "rev-parse", "-q", "--verify", f"refs/heads/{name}", runner=runner)
        if rc == 0:
            return name
    rc, out = _git(repo, "symbolic-ref", "--short", "-q", "HEAD", runner=runner)
    return out.strip()


def irreplaceable_ignored(wt: Path, runner) -> list[str]:
    """Git-ignored paths in the worktree that may be the only copy: anything that is not a
    known cache, a package/build folder without a manifest to rebuild it, or a build
    folder that holds a nested git repo. A failed git call blocks too."""
    rc, out = _git(wt, "status", "--porcelain", "--ignored", runner=runner, timeout=60)
    if rc != 0:
        return ["(git status --ignored failed)"]
    bad = []
    for line in out.splitlines():
        if not line.startswith("!! "):
            continue
        rel = line[3:].strip().strip('"').rstrip("/")
        parts = rel.split("/")
        if rel.endswith(".pyc") or any(p in _CACHES for p in parts):
            continue
        hit = next((i for i, p in enumerate(parts) if p in _NEEDS_MANIFEST), None)
        if hit is None:
            bad.append(rel)
            continue
        folder = wt.joinpath(*parts[:hit + 1])
        if folder.is_symlink() or lab_health.rebuild_command(wt, folder) is None:
            bad.append(rel + " (no manifest to rebuild it)")
        elif parts[hit] not in _PACKAGE_DIRS and folder.is_dir() and _has_nested_git(folder):
            bad.append(rel + " (holds a nested git repo or too many files to check)")
    return bad


def judge(wt: dict, lab_root: Path, *, now: float, min_days: int = MIN_AGE_DAYS,
          cwds: list[str] | None, runner=subprocess.run) -> list[str]:
    """Reasons this worktree is NOT offered. Empty list = every gate passed."""
    path, repo = Path(wt["path"]), Path(wt["repo"])
    if not path.is_dir():
        return ["folder is missing"]
    why: list[str] = []
    if path.is_symlink() or not _under(path, lab_root):
        return ["not a plain folder inside the lab root"]
    if wt.get("locked"):
        why.append("locked (git worktree lock)")
    if os.path.realpath(path.parent) == os.path.realpath(lab_root / "active"):
        why.append("a project folder under active/, not a scratch worktree")
    rc, out = _git(path, "status", "--porcelain", runner=runner)
    if rc != 0:
        why.append("git status failed")
    elif out.strip():
        why.append(f"{len(out.splitlines())} uncommitted or untracked files")
    odd = irreplaceable_ignored(path, runner)
    if odd:
        more = f" (+{len(odd) - 3} more)" if len(odd) > 3 else ""
        why.append("ignored files that are not caches: " + ", ".join(odd[:3]) + more)
    head = wt.get("head", "")
    base = default_branch(repo, runner)
    merged = False
    if head:
        for ref in [r for r in (base, f"origin/{base}" if base else "") if r]:
            rc, _ = _git(repo, "merge-base", "--is-ancestor", head, ref, runner=runner)
            if rc == 0:
                merged = True
                break
        if not merged:
            rc, out = _git(repo, "branch", "-r", "--contains", head, runner=runner)
            merged = rc == 0 and bool(out.strip())
    if not merged:
        rc, out = _git(repo, "rev-list", "--count", f"{base}..{head}", runner=runner) \
            if base and head else (1, "")
        n = out.strip() if rc == 0 else "some"
        why.append(f"{n} commit(s) not merged into {base or 'the main branch'} or pushed")
    newest = _newest_edit(path, runner)
    days = int((now - newest) // 86400) if newest else None
    if days is None:
        why.append("last activity unknown")
    elif days < min_days:
        why.append(f"touched {days} day(s) ago (offered after {min_days})")
    if cwds is None:
        why.append("cannot tell what is running (lsof failed)")
    else:
        for c in cwds:
            if _under(c, path):
                why.append("a running process is working inside it")
                break
    return why


def scan_worktrees(lab_root: Path, *, min_days: int = MIN_AGE_DAYS, now: float | None = None,
                   cwds=_AUTO, runner=subprocess.run) -> list[dict]:
    """One row per worktree: path, repo, branch, kb, reasons, eligible. Offered ones first."""
    now = time.time() if now is None else now
    cwds = cwd_snapshot() if cwds is _AUTO else cwds
    rows = []
    for wt in list_worktrees(lab_root, runner):
        reasons = judge(wt, lab_root, now=now, min_days=min_days, cwds=cwds, runner=runner)
        path = Path(wt["path"])
        try:
            rel = str(path.resolve().relative_to(Path(lab_root).resolve()))
        except ValueError:
            rel = str(path)
        rows.append({"path": path, "rel": rel, "repo": Path(wt["repo"]), "branch": wt.get("branch", ""),
                     "head": wt.get("head", ""), "locked": bool(wt.get("locked")),
                     "kb": lab_health._du_kb(path) if path.is_dir() else 0,
                     "reasons": reasons, "eligible": not reasons})
    rows.sort(key=lambda r: (not r["eligible"], -r["kb"]))
    return rows


def records_dir() -> Path:
    return lab_health.records_dir().parent / "worktree_records"


def write_record(item: dict, out_dir: Path | None = None, now: float | None = None) -> Path:
    """How to get the worktree back. Raises OSError; the caller must then not remove it."""
    now = time.time() if now is None else now
    out_dir = Path(out_dir or records_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    target = item["branch"] or item["head"]
    rec = {"repo": str(item["repo"]), "path": str(item["path"]), "branch": item["branch"],
           "head": item["head"], "kb": item.get("kb", 0), "created": now,
           "restore": "git -C {} worktree add {} {}".format(
               *(shlex.quote(str(x)) for x in (item["repo"], item["path"], target)))}
    stem = f"{Path(item['repo']).name}__{Path(item['path']).name}__{int(now)}"
    path, n = out_dir / f"{stem}.json", 1
    while path.exists():
        n += 1
        path = out_dir / f"{stem}_{n}.json"
    path.write_text(json.dumps(rec, indent=1))
    try:   # branch and path names are nobody else's business
        os.chmod(out_dir, 0o700)
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def remove_worktree(item: dict, lab_root: Path, *, min_days: int = MIN_AGE_DAYS,
                    cwds=_AUTO, out_dir: Path | None = None,
                    now: float | None = None, runner=subprocess.run) -> tuple[bool, str]:
    """Re-check every gate now (the scan may be old), write the restore record, then
    `git worktree remove` without --force. The branch stays."""
    now = time.time() if now is None else now
    wt = {"path": str(item["path"]), "repo": str(item["repo"]), "head": item.get("head", ""),
          "locked": item.get("locked", False)}
    live = next((w for w in list_worktrees(lab_root, runner)
                 if os.path.realpath(w["path"]) == os.path.realpath(wt["path"])), None)
    if live is None:
        return False, "no longer a worktree of a lab repo"
    wt = {**live, "head": live.get("head", "")}
    def check():
        return judge(wt, lab_root, now=now, min_days=min_days,
                     cwds=cwd_snapshot() if cwds is _AUTO else cwds, runner=runner)

    why = check()
    if why:
        return False, "kept: " + "; ".join(why)
    full = {**item, "head": wt["head"], "branch": wt.get("branch", ""),
            "repo": Path(wt["repo"]), "path": Path(wt["path"])}
    try:
        write_record(full, out_dir, now)
    except OSError as e:
        return False, f"restore record not saved ({e}); left in place"
    why = check()   # again right before removing: the record and scan took time
    if why:
        return False, "kept: " + "; ".join(why)
    try:   # no --force: git itself refuses a dirty or locked worktree
        r = runner(["git", *_SAFE_GIT, "-C", wt["repo"], "worktree", "remove", "--", wt["path"]],
                   capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"left in place: {e}"
    if r.returncode != 0:
        msg = (r.stderr.strip().splitlines() or ["git worktree remove failed"])[-1]
        return False, "left in place: " + msg
    return True, "removed; branch kept. Restore: git worktree add (see worktree_records/)"
