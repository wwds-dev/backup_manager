"""Lab root checks, no Qt: what sits at the lab root that should not, report only.

See docs/specs/lab-root-checks.md. Six rules ported from the lab's `folder_audit.py`:
R1 an unexpected root file or folder, R2 a stale-looking root file, R3 a lingering `_to_delete/`,
R4 an empty top-level folder, R5 an `active/*` project not named in AGENTS.md or README.md,
R6 a root or `active/*` symlink that does not resolve.

Reads only: directory listings, `lstat`, and the two Markdown files. It never opens a file for
writing, runs no subprocess and makes no network call. A symlink is listed from its own `lstat`
and is never listed into, walked or opened, so one pointing out of the lab is not followed
(one `os.stat` on the link itself tells whether it resolves; nothing more is read through it).
A finding is a dict: rule, path (absolute), rel (relative to the lab), size (bytes, None when too
big to measure), age_days, why (one line). Nothing here fixes anything.
"""
from __future__ import annotations

import errno
import fnmatch
import os
import re
import stat
import time
from pathlib import Path

_WALK_CAP = 50000          # directory entries per measured folder, as workspace_extra._WALK_CAP
_DOC_READ_CAP = 2_000_000  # bytes read from each of AGENTS.md and README.md
_DOC_NAMES = ("AGENTS.md", "README.md")

ALWAYS_OK = {
    ".DS_Store", ".git", ".claude", ".codex", ".gitignore",
    "folder_audit_report.html", "folder_audit.py",
    # structural, never worth flagging whatever the docs say
    "active", "AGENTS.md", "README.md", "CLAUDE.md",
    # has its own rule (R3)
    "_to_delete",
}
DISPOSABLE_DIR_NAMES = {
    ".venv", "venv", "env", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".ipynb_checkpoints", ".git",
}
STALE_PATTERNS_ROOT = ["*.bak", "*.bak_*", "*~", "*.orig", "*.tmp", "patch_*.py", "fix_*.py", "_patch*.py"]
_BACKTICK_SPAN = re.compile(r"`([^`\n]+)`")


def _lstat(path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except OSError:
        return None


def _read_doc(path: Path) -> str:
    """One of the two docs, as text. A symlink, a non-file or an unreadable file counts as empty."""
    st = _lstat(path)
    if st is None or not stat.S_ISREG(st.st_mode):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(_DOC_READ_CAP)
    except OSError:
        return ""


def _docs(lab_root: Path) -> tuple[set[str], str]:
    """(names in backtick spans of AGENTS.md and README.md, their joined text)."""
    names: set[str] = set()
    parts = []
    for doc in _DOC_NAMES:
        text = _read_doc(lab_root / doc)
        parts.append(text)
        for m in _BACKTICK_SPAN.finditer(text):
            for word in m.group(1).strip().split():
                token = word.rstrip("/").rstrip(".,;:")
                if not token or not re.search(r"[A-Za-z0-9]", token):
                    continue
                names.add(token)
                if "/" in token:
                    # every path segment, so `active/projA/` also names `active` and `projA`
                    names.update(seg for seg in token.split("/") if seg)
    return names, "\n".join(parts)


def _entries(folder: Path) -> list[os.DirEntry]:
    try:
        with os.scandir(folder) as it:
            return sorted(it, key=lambda e: e.name)
    except OSError:
        return []


def _is_link(e: os.DirEntry) -> bool:
    return e.is_symlink()


def _is_real_dir(e: os.DirEntry) -> bool:
    try:
        return e.is_dir(follow_symlinks=False)
    except OSError:
        return False


def _is_real_file(e: os.DirEntry) -> bool:
    try:
        return e.is_file(follow_symlinks=False)
    except OSError:
        return False


def _is_empty_dir(path: str) -> bool | None:
    """True when a real folder has no entries; None when it cannot be listed."""
    try:
        with os.scandir(path) as it:
            return next(it, None) is None
    except OSError:
        return None


def _broken_link(e: os.DirEntry) -> bool:
    """A symlink whose target does not resolve. One stat on the link; nothing is read through it."""
    try:
        os.stat(e.path)
        return False
    except (FileNotFoundError, NotADirectoryError):
        return True
    except OSError as err:
        return err.errno == errno.ELOOP


def _measure(path: str) -> tuple[int | None, int, float | None]:
    """(bytes, file count, oldest file mtime) of a real folder; bytes None when over the walk cap.
    Symlinks inside are counted by their own size and never descended."""
    total = files = seen = 0
    oldest: float | None = None
    for dirpath, dirs, names in os.walk(path, followlinks=False):
        for n in dirs + names:
            seen += 1
            if seen > _WALK_CAP:
                return None, files, oldest
        for n in names:
            st = _lstat(os.path.join(dirpath, n))
            if st is None:
                continue
            total += st.st_size
            files += 1
            oldest = st.st_mtime if oldest is None else min(oldest, st.st_mtime)
    return total, files, oldest


def _size_age(e: os.DirEntry, now: float) -> tuple[int | None, int]:
    st = _lstat(e.path)
    if st is None:
        return 0, 0
    age = max(0, int((now - st.st_mtime) / 86400))
    if _is_real_dir(e):
        return _measure(e.path)[0], age
    return st.st_size, age


def _finding(rule: str, lab_root: Path, e: os.DirEntry, why: str, now: float,
             size_age: tuple[int | None, int] | None = None) -> dict:
    size, age = size_age if size_age is not None else _size_age(e, now)
    return {"rule": rule, "path": e.path, "rel": os.path.relpath(e.path, lab_root),
            "size": size, "age_days": age, "why": why}


def scan(lab_root, now: float | None = None) -> list[dict]:
    """All findings, ordered R1 to R6 and by name within a rule. Never raises on a bad listing."""
    lab_root = Path(lab_root)
    now = time.time() if now is None else now
    known, doc_text = _docs(lab_root)
    root = _entries(lab_root)
    out: list[dict] = []

    # R1: not named in AGENTS.md or README.md, not a dotfile. An empty folder is R4's, a broken
    # symlink is R6's: one fact is not reported twice.
    for e in root:
        if e.name in ALWAYS_OK or e.name.startswith(".") or e.name in known:
            continue
        if _is_real_dir(e) and _is_empty_dir(e.path):
            continue
        if _is_link(e) and _broken_link(e):
            continue
        kind = "folder" if _is_real_dir(e) else "file"
        out.append(_finding("R1", lab_root, e, f"Unexpected {kind} at the lab root: not named in "
                            "AGENTS.md or README.md. Check where it belongs.", now))

    # R2: stale-looking root files (a symlink is never one: it is not a file of this lab)
    for e in root:
        if _is_real_file(e) and any(fnmatch.fnmatch(e.name, p) for p in STALE_PATTERNS_ROOT):
            out.append(_finding("R2", lab_root, e, "Stale-looking leftover (backup copy or one-off "
                                "patch script) at the lab root.", now))

    # R3: a lingering _to_delete/ (a symlink of that name is listed, never walked)
    for e in root:
        if e.name == "_to_delete":
            if _is_real_dir(e):
                size, files, oldest = _measure(e.path)
                old = max(0, int((now - oldest) / 86400)) if oldest is not None else 0
                out.append(_finding("R3", lab_root, e, f"`_to_delete/` still exists ({files} file(s), "
                                    f"oldest {old} days old): clear it out or confirm it is under review.",
                                    now, (size, old)))
            else:
                out.append(_finding("R3", lab_root, e, "`_to_delete` exists (not a folder): clear it out "
                                    "or confirm it is under review.", now))

    # R4: an empty top-level folder; never inside active/ projects
    for e in root:
        if (not _is_real_dir(e) or e.name.startswith(".") or e.name in DISPOSABLE_DIR_NAMES
                or e.name == "active"):
            continue
        if _is_empty_dir(e.path):
            out.append(_finding("R4", lab_root, e, "Empty top-level folder: start using it or remove it.", now))

    # R5 and R6: active/* projects (one level only)
    for e in _entries(lab_root / "active"):
        if e.name.startswith("."):
            continue
        if _is_link(e):
            if _broken_link(e):
                continue                      # R6 below
        elif not _is_real_dir(e):
            continue
        if f"`{e.name}" not in doc_text:
            what = "a symlink" if _is_link(e) else "a project"
            out.append(_finding("R5", lab_root, e, f"`active/{e.name}` ({what}) is not named in "
                                "AGENTS.md or README.md: add a one-line entry.", now))

    # R6: broken symlinks at the lab root and directly under active/
    for e in root + _entries(lab_root / "active"):
        if _is_link(e) and not e.name.startswith(".") and _broken_link(e):
            try:
                target = os.readlink(e.path)
            except OSError:
                target = "?"
            out.append(_finding("R6", lab_root, e, f"Symlink does not resolve (-> {target}): the target "
                                "moved or was deleted, or this runs without access to it.", now))

    out.sort(key=lambda f: (f["rule"], f["rel"]))
    return out
