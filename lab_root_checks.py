"""Lab root checks, no Qt: what sits at the lab root that should not, report only.

See docs/specs/lab-root-checks.md. Six rules ported from the lab's `folder_audit.py`:
R1 an unexpected root file or folder, R2 a stale-looking root file, R3 a lingering `_to_delete/`,
R4 an empty top-level folder, R5 an `active/*` project not named in AGENTS.md or README.md,
R6 a root or `active/*` symlink that does not resolve.

Reads only: directory listings, `lstat`, and the two Markdown files. It never opens a file for
writing, runs no subprocess and makes no network call. A symlink is listed from its own `lstat`
and is never listed into, walked or opened, so one pointing out of the lab is not followed
(one `os.stat` on the link itself tells whether it resolves; nothing more is read through it).
A finding is a dict: rule, path (absolute), rel (relative to the lab), size (bytes; None when it
is not known), age_days (None when the entry vanished), partial (True when `size` is only a lower
bound or unknown because of the walk cap, an unreadable folder or a vanished file), why (one line).
The rule is R1 to R6, or NOTE for something that was not checked (a doc that could not be read, a
symlink pointing out of the lab and the home folder, a failed scan). Nothing here fixes anything.
"""
from __future__ import annotations

import errno
import fnmatch
import os
import re
import stat
import time
import unicodedata
from collections import deque
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


def _nfc(text: str) -> str:
    """Names compare as NFC: the disk may hold NFD (a Mac file name) while the docs hold NFC."""
    return unicodedata.normalize("NFC", text)


def _lstat(path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except OSError:
        return None


def _read_doc(path: Path) -> str | None:
    """One of the two docs, as text. "" when it does not exist; None when it exists but was not read
    (a symlink, a non-file such as a FIFO, no permission). Opened without following a link and without
    blocking, then checked on the descriptor, so a swap between check and open cannot hang or leak."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None if os.path.lexists(path) else ""      # a dangling link exists but is not read
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            return None
        f = os.fdopen(fd, "r", encoding="utf-8", errors="ignore")
    except OSError:
        os.close(fd)
        return None
    try:
        with f:
            return f.read(_DOC_READ_CAP)
    except OSError:
        return None


def _docs(lab_root: Path) -> tuple[set[str], str, list[str]]:
    """(names in backtick spans of AGENTS.md and README.md as NFC, their joined NFC text, the docs
    that exist but were not read)."""
    names: set[str] = set()
    parts = []
    unread = []
    for doc in _DOC_NAMES:
        text = _read_doc(lab_root / doc)
        if text is None:
            unread.append(doc)
            continue
        text = _nfc(text)
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
    return names, "\n".join(parts), unread


def _entries(folder: Path) -> list[os.DirEntry]:
    try:
        with os.scandir(folder) as it:
            return sorted(it, key=lambda e: e.name)
    except OSError:
        return []


def _active_entries(lab_root: Path) -> list[os.DirEntry]:
    """What is directly under `active/`; nothing when `active` is not a real folder (a symlinked
    `active` is not followed)."""
    st = _lstat(lab_root / "active")
    if st is None or not stat.S_ISDIR(st.st_mode):
        return []
    return _entries(lab_root / "active")


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


_MAX_HOPS = 40


def _roots(lab_root: Path) -> tuple[str, ...]:
    """Where a symlink may point and still be checked: the lab and the home folder (real paths)."""
    return (os.path.realpath(lab_root), os.path.realpath(os.path.expanduser("~")))


def _allowed(p: str, roots: tuple[str, ...]) -> bool:
    """Inside a root, or a folder above one (it has to be passed through to get there)."""
    return any(p == r or p.startswith(r.rstrip(os.sep) + os.sep) or r.startswith(p.rstrip(os.sep) + os.sep)
               for r in roots)


def _link_state(e: os.DirEntry, roots: tuple[str, ...]) -> str:
    """Does a symlink resolve? "ok", "broken" or "unchecked". The link is followed by hand, one component
    at a time with `lstat`, and nothing outside the lab and the home folder is touched (a network or
    autofs target could hang a stat): a link leading out of them, however many hops, is "unchecked"."""
    cur = os.path.realpath(os.path.dirname(e.path))
    try:
        first = os.readlink(e.path)
    except OSError:
        return "unchecked"
    todo = deque(c for c in first.split(os.sep) if c)
    if first.startswith(os.sep):
        cur = os.sep
    hops = 1
    while todo:
        comp = todo.popleft()
        if comp == ".":
            continue
        if comp == "..":
            cur = os.path.dirname(cur)
            continue
        nxt = os.path.join(cur, comp)
        if not _allowed(nxt, roots):
            return "unchecked"
        try:
            st = os.lstat(nxt)
        except (FileNotFoundError, NotADirectoryError):
            return "broken"
        except OSError as err:
            return "broken" if err.errno == errno.ELOOP else "unchecked"
        if stat.S_ISLNK(st.st_mode):
            hops += 1
            if hops > _MAX_HOPS:
                return "broken"                    # a loop
            try:
                target = os.readlink(nxt)
            except OSError:
                return "unchecked"
            if target.startswith(os.sep):
                cur = os.sep
            todo.extendleft(reversed([c for c in target.split(os.sep) if c]))
        else:
            cur = nxt
    return "ok"


def _measure(path: str) -> tuple[int | None, int, float | None, bool]:
    """(bytes, file count, oldest file mtime, partial) of a real folder. bytes is None when it is not
    known: over the walk cap, the top is not a real folder (a link swapped in) or cannot be listed.
    partial is True whenever the numbers are a lower bound or unknown: the cap, an unreadable subfolder,
    a file that vanished. A symlink to a file is counted by its own size; a symlink to a folder is
    neither counted nor descended."""
    st = _lstat(path)
    if st is None or not stat.S_ISDIR(st.st_mode):
        return None, 0, None, True
    total = files = seen = 0
    oldest: float | None = None
    partial = False
    top_failed = False

    def onerror(err: OSError) -> None:
        nonlocal partial, top_failed
        partial = True
        if err.filename == path:
            top_failed = True

    for dirpath, dirs, names in os.walk(path, followlinks=False, onerror=onerror):
        for n in dirs + names:
            seen += 1
            if seen > _WALK_CAP:
                return None, files, oldest, True
        for n in names:
            st = _lstat(os.path.join(dirpath, n))
            if st is None:
                partial = True
                continue
            total += st.st_size
            files += 1
            oldest = st.st_mtime if oldest is None else min(oldest, st.st_mtime)
    if top_failed:
        return None, files, oldest, True
    return total, files, oldest, partial


def _age(st: os.stat_result, now: float) -> int:
    return max(0, int((now - st.st_mtime) / 86400))


def _size_age(path: str, now: float, measure: bool = True) -> tuple[int | None, int | None, bool]:
    """(size, age_days, partial) from the entry's own `lstat`. A vanished entry is (None, None, True).
    A folder is measured only when `measure` (R5 rows are not: a project can hold a .venv)."""
    st = _lstat(path)
    if st is None:
        return None, None, True
    age = _age(st, now)
    if stat.S_ISDIR(st.st_mode):
        if not measure:
            return None, age, False
        size, _, _, partial = _measure(path)
        return size, age, partial
    return st.st_size, age, False


def _finding(rule: str, lab_root: Path, path: str, why: str, now: float,
             size_age: tuple[int | None, int | None, bool] | None = None) -> dict:
    size, age, partial = size_age if size_age is not None else _size_age(path, now)
    return {"rule": rule, "path": path, "rel": os.path.relpath(path, lab_root),
            "size": size, "age_days": age, "partial": partial, "why": why}


def scan_safe(lab_root, now: float | None = None) -> list[dict]:
    """`scan`, but a failure inside it becomes one NOTE row instead of an exception, so the Workspace
    dialog and the weekly report keep their other parts."""
    try:
        return scan(lab_root, now=now)
    except Exception as err:       # a bug or an odd file system must not cost the caller its other results
        return [{"rule": "NOTE", "path": str(lab_root), "rel": ".", "size": None, "age_days": None,
                 "partial": False,
                 "why": f"The lab root scan failed ({type(err).__name__}): nothing was checked."}]


def scan(lab_root, now: float | None = None) -> list[dict]:
    """All findings, ordered by rule (R1 to R6, then NOTE) and by name within a rule. Never raises on a
    bad listing."""
    lab_root = Path(lab_root)
    now = time.time() if now is None else now
    known, doc_text, unread = _docs(lab_root)
    root = _entries(lab_root)
    active = _active_entries(lab_root)
    roots = _roots(lab_root)
    states: dict[str, str] = {}

    def link_state(e: os.DirEntry) -> str:
        if e.path not in states:
            states[e.path] = _link_state(e, roots) if _is_link(e) else "ok"
        return states[e.path]

    out: list[dict] = []

    # A doc that exists but was not read (a symlink, a FIFO) leaves R1 and R5 without their list of
    # names: say so once and skip both, instead of flagging everything.
    for doc in unread:
        out.append(_finding("NOTE", lab_root, str(lab_root / doc), f"`{doc}` is a symlink or could not "
                            "be read, so it was not read: R1 and R5 were not checked.", now,
                            _size_age(str(lab_root / doc), now, measure=False)))

    # R1: not named in AGENTS.md or README.md, not a dotfile. An empty folder is R4's, a broken
    # symlink is R6's: one fact is not reported twice.
    for e in ([] if unread else root):
        if e.name in ALWAYS_OK or e.name.startswith(".") or _nfc(e.name) in known:
            continue
        if _is_real_dir(e) and _is_empty_dir(e.path):
            continue
        if _is_link(e) and link_state(e) == "broken":
            continue
        kind = "folder" if _is_real_dir(e) else "file"
        out.append(_finding("R1", lab_root, e.path, f"Unexpected {kind} at the lab root: not named in "
                            "AGENTS.md or README.md. Check where it belongs.", now))

    # R2: stale-looking root files (a symlink is never one: it is not a file of this lab; a dotfile
    # such as `.hid.bak` is one: only R1 leaves dotfiles alone)
    for e in root:
        if _is_real_file(e) and any(fnmatch.fnmatch(e.name, p) for p in STALE_PATTERNS_ROOT):
            out.append(_finding("R2", lab_root, e.path, "Stale-looking leftover (backup copy or one-off "
                                "patch script) at the lab root.", now))

    # R3: a lingering _to_delete/ (a symlink of that name is listed, never walked; a broken one is R6's)
    for e in root:
        if e.name != "_to_delete":
            continue
        if _is_real_dir(e):
            size, files, oldest, partial = _measure(e.path)
            st = _lstat(e.path)
            own_age = _age(st, now) if st is not None else None
            if size is None:
                detail = f"not measured: more than {_WALK_CAP} entries, or not readable"
                age = own_age
            else:
                old = max(0, int((now - oldest) / 86400)) if oldest is not None else 0
                if partial:
                    detail = f"at least {files} file(s) seen, oldest seen {old} days old"
                else:
                    detail = f"{files} file(s), oldest {old} days old"
                age = old
            out.append(_finding("R3", lab_root, e.path, f"`_to_delete/` still exists ({detail}): clear it "
                                "out or confirm it is under review.", now, (size, age, partial)))
        elif _is_link(e):
            if link_state(e) != "broken":
                out.append(_finding("R3", lab_root, e.path, "`_to_delete` exists as a symlink (not walked): "
                                    "clear it out or confirm it is under review.", now))
        else:
            out.append(_finding("R3", lab_root, e.path, "`_to_delete` exists as a file, not a folder: clear "
                                "it out or confirm it is under review.", now))

    # R4: an empty top-level folder; never inside active/ projects (an empty _to_delete/ is R3's)
    for e in root:
        if (not _is_real_dir(e) or e.name.startswith(".") or e.name in DISPOSABLE_DIR_NAMES
                or e.name in ("active", "_to_delete")):
            continue
        if _is_empty_dir(e.path):
            out.append(_finding("R4", lab_root, e.path, "Empty top-level folder: start using it or remove it.", now))

    # R5: active/* projects (one level only). The name must follow a backtick in the docs: a prefix
    # match, as in Folder Audit (`labx` also covers `lab`). Not measured: a project holds .venv trees.
    for e in ([] if unread else active):
        if e.name.startswith("."):
            continue
        if _is_link(e):
            if link_state(e) == "broken":
                continue                      # R6 below
        elif not _is_real_dir(e):
            continue
        if f"`{_nfc(e.name)}" not in doc_text:
            what = "a symlink" if _is_link(e) else "a project"
            out.append(_finding("R5", lab_root, e.path, f"`active/{e.name}` ({what}) is not named in "
                                "AGENTS.md or README.md: add a one-line entry.", now,
                                _size_age(e.path, now, measure=False)))

    # R6: broken symlinks at the lab root and directly under active/
    for e in root + active:
        if _is_link(e) and not e.name.startswith(".") and link_state(e) == "broken":
            try:
                target = os.readlink(e.path)
            except OSError:
                target = "?"
            out.append(_finding("R6", lab_root, e.path, f"Symlink does not resolve (-> {target}): the target "
                                "moved or was deleted, or this runs without access to it.", now))

    # A link that leads out of the lab and the home folder is not followed, so not checked. Said once,
    # and only when no other row already lists it.
    listed = {f["path"] for f in out}
    for e in root + active:
        if _is_link(e) and not e.name.startswith(".") and e.path not in listed and link_state(e) == "unchecked":
            try:
                target = os.readlink(e.path)
            except OSError:
                target = "?"
            out.append(_finding("NOTE", lab_root, e.path, f"Symlink (-> {target}) leads outside the lab and "
                                "the home folder: not checked, so whether it resolves is unknown.", now))

    out.sort(key=lambda f: (f["rule"] == "NOTE", f["rule"], f["rel"]))
    return out
