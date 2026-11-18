"""Workspace cleanup, slice 2, no Qt: backup snapshots, archive listing, root caches, weekly report.

See docs/specs/workspace-cleanup.md sections 14-15. A backup snapshot is offered only when it is
older than BACKUP_MIN_DAYS and no non-history doc names it; it goes to the Trash (the mover is
passed in, never rmtree) after a record is written. The report scan deletes nothing.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import lab_health
import workspace

BACKUP_MIN_DAYS = 30
WEEKLY_DAYS = 7
_WALK_CAP = 50000
_FILE_CAP = 2_000_000      # bytes; larger docs are not searched (and block, see below)
_DOC_CAP = 5000
_DOC_SUFFIX = {".md", ".txt", ".sh", ".py", ".toml", ".json", ".yml", ".yaml", ".command"}
_DOC_SKIP_PARTS = {"history", ".git", "node_modules", ".venv", "venv", ".claude", "archive", "backups"}
# Never walked or cleaned for caches: other agents' trees and the dirs with their own rules.
_NO_CACHE_ROOTS = {"active", ".claude", "archive", "backups", "worktrees", ".git", "runners",
                   "_to_delete"}
_SELF_SPEC = "workspace-cleanup.md"   # this spec lists every snapshot while describing the rule


def _write_private(path: Path, text: str) -> None:
    """Create with mode 600 from the start (no window where it is world-readable)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)


def clamp_days(value, lo: int, hi: int, default: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(lo, min(hi, v))


def _birth(folder: Path) -> float:
    """When the folder itself was created here (a copy made with `cp -a` keeps old mtimes)."""
    try:
        st = os.lstat(folder)
    except OSError:
        return time.time()
    return max(getattr(st, "st_birthtime", 0.0), st.st_ctime)


def _newest_mtime(folder: Path) -> float | None:
    """Youngest sign of life: newest mtime inside, or when the folder was created here.
    None when the folder is too big to look through (fail closed: age unknown)."""
    try:
        newest = max(os.lstat(folder).st_mtime, _birth(folder))
    except OSError:
        return None
    seen = 0
    for dirpath, dirs, files in os.walk(folder):
        for n in dirs + files:
            seen += 1
            if seen > _WALK_CAP:
                return None
            try:
                newest = max(newest, os.lstat(os.path.join(dirpath, n)).st_mtime)
            except OSError:
                pass
    return newest


def _doc_files(lab_root: Path):
    """Non-history docs a snapshot may be named in. Yields paths; raises OSError on failure."""
    cands = [lab_root / "AGENTS.md"]
    roots = [lab_root / "docs"]
    active = lab_root / "active"
    if active.is_dir():
        for p in sorted(active.iterdir()):
            if p.is_dir() and not p.is_symlink():
                cands += [p / "AGENTS.md", p / "TODO.md"]
                roots.append(p / "docs")
    for c in cands:
        if c.is_file() and not c.is_symlink():
            yield c
    n = 0
    for r in roots:
        if not r.is_dir() or r.is_symlink():
            continue
        for dirpath, dirs, files in os.walk(r):
            dirs[:] = [d for d in dirs if d not in _DOC_SKIP_PARTS]
            for f in files:
                p = Path(dirpath) / f
                if (p.suffix in _DOC_SUFFIX and not f.startswith("lab-notes-")
                        and f != _SELF_SPEC and not p.is_symlink() and p.is_file()):
                    n += 1
                    if n > _DOC_CAP:
                        raise OSError("too many docs to search")
                    yield p


def backup_references(name: str, lab_root: Path) -> list[str] | None:
    """Docs (relative paths) that name the snapshot, or None when the search could not finish
    (a doc too big or unreadable counts as a failure: fail closed)."""
    needles = {name, name.removesuffix(".noindex")}
    hits: list[str] = []
    try:
        for p in _doc_files(lab_root):
            if p.stat().st_size > _FILE_CAP:
                return None
            text = p.read_text(errors="ignore")
            if any(n in text for n in needles):
                hits.append(str(p.relative_to(lab_root)))
    except (OSError, ValueError):
        return None
    return hits


def scan_backups(lab_root: Path, *, min_days: int = BACKUP_MIN_DAYS, now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    bdir = lab_root / "backups"
    rows = []
    if not bdir.is_dir() or bdir.is_symlink():
        return rows
    for p in sorted(bdir.iterdir()):
        if p.name.startswith("."):
            continue
        why: list[str] = []
        refs: list[str] = []
        if p.is_symlink() or not p.is_dir() or not workspace._under(p, lab_root):
            why.append("not a plain folder inside backups/")
            days, kb = None, 0
        else:
            newest = _newest_mtime(p)
            days = int((now - newest) // 86400) if newest else None
            kb = lab_health._du_kb(p)
            if days is None:
                why.append("age unknown")
            elif days < min_days:
                why.append(f"only {days} day(s) old (offered after {min_days})")
            found = backup_references(p.name, lab_root)
            if found is None:
                why.append("could not search the docs for a reference")
            elif found:
                refs = found
                why.append("named in " + ", ".join(found[:3]) + (f" (+{len(found) - 3})" if len(found) > 3 else ""))
        rows.append({"path": p, "rel": f"backups/{p.name}", "kb": kb, "days": days, "refs": refs,
                     "reasons": why, "eligible": not why})
    rows.sort(key=lambda r: (not r["eligible"], -r["kb"]))
    return rows


def backup_records_dir() -> Path:
    return lab_health.records_dir().parent / "backup_records"


def write_backup_record(item: dict, out_dir: Path | None = None, now: float | None = None) -> Path:
    """Raises OSError; the caller must then not trash the snapshot."""
    now = time.time() if now is None else now
    out_dir = Path(out_dir or backup_records_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    rec = {"path": str(item["path"]), "kb": item.get("kb", 0), "days": item.get("days"),
           "created": now, "restore": "Finder: Trash > Put Back"}
    stem, n = f"{Path(item['path']).name}__{int(now)}", 1
    path = out_dir / f"{stem}.json"
    while path.exists():
        n += 1
        path = out_dir / f"{stem}_{n}.json"
    _write_private(path, json.dumps(rec, indent=1))
    try:
        os.chmod(out_dir, 0o700)
    except OSError:
        pass
    return path


def trash_backup(item: dict, lab_root: Path, mover, *, min_days: int = BACKUP_MIN_DAYS,
                 out_dir: Path | None = None, now: float | None = None) -> tuple[bool, str]:
    """Re-check the gates now, write the record, then mover(path) -> bool (Trash)."""
    now = time.time() if now is None else now
    p = Path(item["path"])
    if p.parent.name != "backups" or os.path.realpath(p.parent) != os.path.realpath(lab_root / "backups"):
        return False, "not a snapshot directly under backups/"
    row = next((r for r in scan_backups(lab_root, min_days=min_days, now=now) if r["path"] == p), None)
    if row is None:
        return False, "no longer there"
    if not row["eligible"]:
        return False, "kept: " + "; ".join(row["reasons"])
    try:
        write_backup_record({**row}, out_dir, now)
    except OSError as e:
        return False, f"record not saved ({e}); left in place"
    try:
        ok = mover(str(p))
    except Exception as e:   # noqa: BLE001 - the mover is Qt/OS code
        return False, f"left in place: {e}"
    return (True, "moved to the Trash (Put Back to restore)") if ok else (False, "could not move to the Trash; left in place")


def scan_archive(lab_root: Path, worktree_rows: list[dict] | None = None, *, now: float | None = None) -> list[dict]:
    """Report only: every archive/* entry with size, age and the slice-1 verdict of its git members."""
    now = time.time() if now is None else now
    adir = lab_root / "archive"
    rows = []
    if not adir.is_dir() or adir.is_symlink():
        return rows
    wts = worktree_rows or []
    for p in sorted(adir.iterdir()):
        if p.name.startswith(".") or p.is_symlink() or not p.is_dir():
            continue
        newest = _newest_mtime(p)
        members = [w for w in wts if w["rel"].startswith(f"archive/{p.name}/")]
        rows.append({"path": p, "rel": f"archive/{p.name}", "kb": lab_health._du_kb(p),
                     "days": int((now - newest) // 86400) if newest else None,
                     "git_members": [{"rel": w["rel"], "offered": w["eligible"],
                                      "reasons": w["reasons"]} for w in members]})
    rows.sort(key=lambda r: -r["kb"])
    return rows


def scan_root_caches(lab_root: Path) -> list[dict]:
    """Cache folders in the lab root and one level below top-level scratch folders."""
    out = []
    def add(p: Path):
        if p.is_dir() and not p.is_symlink():
            out.append({"path": p, "rel": str(p.relative_to(lab_root)), "kb": lab_health._du_kb(p)})
    for name in sorted(lab_health.JUNK_NAMES):
        add(lab_root / name)
    for d in sorted(lab_root.iterdir()) if lab_root.is_dir() else []:
        if d.name in _NO_CACHE_ROOTS or d.name.startswith(".") or d.is_symlink() or not d.is_dir():
            continue
        if (d / ".git").exists():     # another repo: not ours to touch
            continue
        for name in sorted(lab_health.JUNK_NAMES):
            add(d / name)
    return out


def clean_caches(paths: list[Path], lab_root: Path) -> list[tuple[Path, bool, str]]:
    """Permanent delete (they regenerate). Every path is re-validated first."""
    res = []
    for p in paths:
        p = Path(p)
        try:
            rel = p.relative_to(lab_root)
        except ValueError:
            res.append((p, False, "outside the lab root"))
            continue
        top = rel.parts[0] if rel.parts else ""
        if (p.name not in lab_health.JUNK_NAMES or p.is_symlink() or not p.is_dir()
                or top in _NO_CACHE_ROOTS or top.startswith(".") or len(rel.parts) > 2
                or any(q.is_symlink() for q in p.relative_to(lab_root).parents for q in [lab_root / q])
                or any((lab_root / Path(*rel.parts[:i]) / ".git").exists() for i in range(1, len(rel.parts)))):
            res.append((p, False, "not an allowed cache folder"))
            continue
        try:
            shutil.rmtree(p)
            res.append((p, True, "deleted"))
        except OSError as e:
            res.append((p, False, str(e)))
    return res


def scan_due(last: float | None, now: float | None = None, days: int = WEEKLY_DAYS) -> bool:
    now = time.time() if now is None else now
    return not isinstance(last, (int, float)) or last > now or now - last >= days * 86400


def build_report(lab_root: Path, *, min_days: int = BACKUP_MIN_DAYS, wt_days: int = workspace.MIN_AGE_DAYS,
                 now: float | None = None, cwds=workspace._AUTO, runner=None) -> dict:
    """Read-only: counts and sizes of what is offered or kept. Deletes and moves nothing."""
    now = time.time() if now is None else now
    kw = {"runner": runner} if runner else {}
    wts = workspace.scan_worktrees(lab_root, min_days=wt_days, now=now, cwds=cwds, **kw)
    backups = scan_backups(lab_root, min_days=min_days, now=now)
    archive = scan_archive(lab_root, wts, now=now)
    caches = scan_root_caches(lab_root)
    def part(rows):
        off = [r for r in rows if r.get("eligible")]
        return {"offered": len(off), "offered_kb": sum(r["kb"] for r in off), "total": len(rows)}
    return {"scanned": now, "worktrees": part(wts), "backups": part(backups),
            "archive": {"entries": len(archive), "kb": sum(r["kb"] for r in archive)},
            "caches": {"folders": len(caches), "kb": sum(r["kb"] for r in caches)},
            "offered_kb": part(wts)["offered_kb"] + part(backups)["offered_kb"]
                          + sum(r["kb"] for r in caches),
            "offered_items": part(wts)["offered"] + part(backups)["offered"] + len(caches)}


def write_report(report: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_private(path, json.dumps(report, indent=1))
    return path
