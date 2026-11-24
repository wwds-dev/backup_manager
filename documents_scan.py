"""Documents space scan, no Qt: where ~/Documents can save space, report only.

See docs/specs/documents-scan.md. One walk of a root folder (default ~/Documents) that lists:
- top:       size and file count of each top-level entry (size on disk, from `st_blocks`);
- large:     files (and macOS bundles such as `.app`, `.photoslibrary`) of LARGE_MIN bytes or more;
- old:       files of OLD_MIN bytes or more not modified for OLD_DAYS days;
- dupes:     groups of byte-identical files of DUPE_MIN bytes or more (size, then a 64 KB head hash,
             then a full hash); `wasted` is what all copies but one take;
- regen:     folders a tool can rebuild (`node_modules`, `.venv`, `__pycache__`, `DerivedData`, ...);
- scattered: folder names that appear in more than one place outside the lab (a sign of a structure
             to consolidate), ignoring generic names such as `src` or `images`;
- notes:     what was not checked (unreadable folders, the entry cap, files not on this Mac).

Reads only: directory listings, `lstat`, and file contents for duplicate candidates. It never opens a
file for writing, runs no subprocess and makes no network call. Symlinks are never followed. A file
whose data is not on this Mac (an iCloud placeholder, `SF_DATALESS`) is never opened, so a scan does not
trigger a download. Hard links to the same inode count once. `.git` folders and bundles are measured
as one item and not walked into for duplicates. Nothing here deletes, moves or renames anything.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

LARGE_MIN = 100 * 1024 * 1024
OLD_MIN = 10 * 1024 * 1024
OLD_DAYS = 730
DUPE_MIN = 1024 * 1024
HEAD_BYTES = 64 * 1024
HASH_BUDGET = 20 * 1024 ** 3      # bytes read in full-file hashing per scan
ENTRY_CAP = 2_000_000             # directory entries per scan
LIST_CAP = 100                    # rows kept per list
SF_DATALESS = 0x40000000          # macOS: file content lives in the cloud only

REGEN_NAMES = {
    "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".nox", "DerivedData", ".next", ".parcel-cache", ".gradle", ".turbo", ".cache",
}
BUNDLE_SUFFIXES = (".app", ".photoslibrary", ".musiclibrary", ".tvlibrary", ".fcpbundle",
                   ".imovielibrary", ".logicx", ".band", ".utm", ".pvm", ".vmwarevm", ".sparsebundle",
                   ".xcarchive", ".framework", ".bundle", ".pkg", ".rtfd")
GENERIC_NAMES = {
    "src", "lib", "libs", "bin", "docs", "doc", "test", "tests", "assets", "images", "img", "static",
    "public", "scripts", "data", "build", "dist", "tmp", "temp", "output", "logs", "config", "resources",
    "templates", "components", "utils", "include", "app", "web", "site", "css", "js", "fonts", "icons",
    "media", "examples", "backup", "backups", "archive", "old", "new", "misc", "files", "notes", "drafts",
    "export", "exports", "source", "sources", "vendor", "packages", "modules", "history", "specs", "audit",
    "legal", "foundry", "agents", "tooling", "playbooks", "screenshots", "fixtures", "migrations",
}
_COPY_TAIL = re.compile(r"(\s+copy(\s+\d+)?|\s*\(\d+\)|[\s_-]+\d+|[\s_-]+(old|new|final|backup|bak))$",
                        re.IGNORECASE)


def _key(name: str) -> str:
    """The comparable form of a folder name: NFC, case-folded, without a 'copy' / ' 2' / '(1)' tail."""
    n = unicodedata.normalize("NFC", name).strip().casefold()
    prev = None
    while prev != n:
        prev, n = n, _COPY_TAIL.sub("", n).strip()
    return n


def _disk(st: os.stat_result) -> int:
    blocks = getattr(st, "st_blocks", None)
    return blocks * 512 if blocks is not None else st.st_size


def _dataless(st: os.stat_result) -> bool:
    return bool(getattr(st, "st_flags", 0) & SF_DATALESS)


def _hash(path: str, limit: int | None) -> str | None:
    h = hashlib.blake2b(digest_size=20)
    try:
        with open(path, "rb", buffering=0) as f:
            left = limit
            while True:
                chunk = f.read(1024 * 1024 if left is None else min(1024 * 1024, left))
                if not chunk:
                    break
                h.update(chunk)
                if left is not None:
                    left -= len(chunk)
                    if left <= 0:
                        break
    except OSError:
        return None
    return h.hexdigest()


def _measure(path: str, budget: list[int]) -> tuple[int, int, bool]:
    """(bytes on disk, files, complete) of a folder, never following links; spends `budget[0]`."""
    total, files, stack = 0, 0, [path]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            return total, files, False
        with it:
            for e in it:
                budget[0] -= 1
                if budget[0] < 0:
                    return total, files, False
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISDIR(st.st_mode):
                    stack.append(e.path)
                else:
                    total += _disk(st)
                    files += 1
    return total, files, True


def _top_of(path: str, root: str) -> str:
    rel = os.path.relpath(path, root)
    return rel.split(os.sep, 1)[0]


def scan_safe(root=None, now: float | None = None, **kw) -> dict:
    """scan(), but a failure becomes a note instead of an exception (the app's worker calls this)."""
    root = str(root or Path.home() / "Documents")
    try:
        return scan(root, now=now, **kw)
    except Exception as exc:  # noqa: BLE001 - report, never crash the app
        return {"root": root, "top": [], "large": [], "old": [], "dupes": [], "regen": [],
                "scattered": [], "totals": {}, "notes": [f"The scan failed: {exc.__class__.__name__}"]}


def scan(root=None, now: float | None = None, *, lab_dir: str | None = None,
         entry_cap: int = ENTRY_CAP, hash_budget: int = HASH_BUDGET) -> dict:
    root = os.path.realpath(str(root or Path.home() / "Documents"))
    now = time.time() if now is None else now
    lab = os.path.realpath(lab_dir) if lab_dir else os.path.join(root, "lab")
    budget = [entry_cap]
    notes: list[str] = []
    top: dict[str, dict] = {}
    large, old, regen = [], [], []
    by_size: dict[int, list[str]] = defaultdict(list)
    seen_inodes: set[tuple[int, int]] = set()
    folders: dict[str, list[str]] = defaultdict(list)
    unreadable = dataless = 0
    total_bytes = total_files = 0

    def add_top(path, size, files=1):
        t = top.setdefault(_top_of(path, root), {"name": _top_of(path, root), "size": 0, "files": 0})
        t["size"] += size
        t["files"] += files

    def item(path, size, st, kind):
        return {"path": path, "rel": os.path.relpath(path, root), "size": size, "kind": kind,
                "age_days": int(max(0, now - st.st_mtime) // 86400)}

    stack = [(root, 0)]
    capped = False
    while stack and not capped:
        d, depth = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            unreadable += 1
            continue
        with it:
            for e in it:
                budget[0] -= 1
                if budget[0] < 0:
                    capped = True
                    break
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISLNK(st.st_mode):
                    continue
                name = e.name
                if stat.S_ISDIR(st.st_mode):
                    is_bundle = name.lower().endswith(BUNDLE_SUFFIXES)
                    is_regen = name in REGEN_NAMES or os.path.isfile(os.path.join(e.path, "pyvenv.cfg"))
                    if name == ".git" or is_bundle or is_regen:
                        size, files, complete = _measure(e.path, budget)
                        total_bytes += size
                        total_files += files
                        add_top(e.path, size, files)
                        if not complete:
                            notes.append(f"Only part of {os.path.relpath(e.path, root)} was measured.")
                        if is_regen and size:
                            r = item(e.path, size, st, "regen")
                            r["in_lab"] = e.path.startswith(lab + os.sep)
                            regen.append(r)
                        elif is_bundle and size >= LARGE_MIN:
                            large.append(item(e.path, size, st, "bundle"))
                        continue
                    if not e.path.startswith(lab + os.sep) and e.path != lab and depth < 5:
                        k = _key(name)
                        if k and k not in GENERIC_NAMES and not name.startswith("."):
                            folders[k].append(e.path)
                    stack.append((e.path, depth + 1))
                    continue
                if not stat.S_ISREG(st.st_mode):
                    continue
                ino = (st.st_dev, st.st_ino)
                if st.st_nlink > 1:
                    if ino in seen_inodes:
                        continue
                    seen_inodes.add(ino)
                size = _disk(st)
                total_bytes += size
                total_files += 1
                add_top(e.path, size)
                if _dataless(st):
                    dataless += 1
                    continue
                logical = st.st_size
                if logical >= LARGE_MIN:
                    large.append(item(e.path, logical, st, "file"))
                if logical >= OLD_MIN and now - st.st_mtime >= OLD_DAYS * 86400:
                    old.append(item(e.path, logical, st, "file"))
                if logical >= DUPE_MIN:
                    by_size[logical].append(e.path)

    if capped:
        notes.append(f"Stopped after {entry_cap:,} entries; totals and lists are partial.")
    if unreadable:
        notes.append(f"{unreadable} folder(s) could not be read and were skipped.")
    if dataless:
        notes.append(f"{dataless} file(s) are not downloaded to this Mac and were not checked.")

    dupes, hb_left = [], [hash_budget]
    for size in sorted((s for s, ps in by_size.items() if len(ps) > 1), reverse=True):
        heads = defaultdict(list)
        for p in by_size[size]:
            h = _hash(p, HEAD_BYTES)
            if h:
                heads[h].append(p)
        for group in heads.values():
            if len(group) < 2:
                continue
            if size <= HEAD_BYTES:
                fulls = {"head": group}
            else:
                if hb_left[0] < size * len(group):
                    notes.append("Hashing budget used up; smaller duplicates were not checked.")
                    hb_left[0] = -1
                    break
                hb_left[0] -= size * len(group)
                fulls = defaultdict(list)
                for p in group:
                    h = _hash(p, None)
                    if h:
                        fulls[h].append(p)
            for paths in fulls.values():
                if len(paths) > 1:
                    paths.sort()
                    dupes.append({"size": size, "count": len(paths), "wasted": size * (len(paths) - 1),
                                  "paths": paths, "rels": [os.path.relpath(p, root) for p in paths],
                                  "in_lab": all(p.startswith(lab + os.sep) for p in paths)})
        if hb_left[0] < 0:
            break

    scattered = []
    for k, paths in folders.items():
        paths = sorted(paths)
        # a folder inside another of the same name ("Tax/Tax 2023") is structure, not scatter
        paths = [p for p in paths if not any(p.startswith(q + os.sep) for q in paths if q != p)]
        if len({os.path.dirname(p) for p in paths}) < 2:
            continue
        scattered.append({"name": k, "count": len(paths), "paths": paths,
                          "rels": [os.path.relpath(p, root) for p in paths]})
    scattered.sort(key=lambda s: (-s["count"], s["name"]))

    by_size_desc = lambda r: -r["size"]  # noqa: E731
    large.sort(key=by_size_desc)
    old.sort(key=by_size_desc)
    regen.sort(key=by_size_desc)
    dupes.sort(key=lambda g: -g["wasted"])
    return {
        "root": root,
        "scanned": now,
        "top": sorted(top.values(), key=by_size_desc),
        "large": large[:LIST_CAP], "old": old[:LIST_CAP], "regen": regen[:LIST_CAP],
        "dupes": dupes[:LIST_CAP], "scattered": scattered[:LIST_CAP],
        "totals": {
            "bytes": total_bytes, "files": total_files,
            "dupes_wasted": sum(g["wasted"] for g in dupes),
            "dupes_outside_lab": sum(g["wasted"] for g in dupes if not g["in_lab"]),
            "regen_bytes": sum(r["size"] for r in regen),
            "regen_outside_lab": sum(r["size"] for r in regen if not r["in_lab"]),
            "old_bytes": sum(r["size"] for r in old),
        },
        "notes": notes,
    }


if __name__ == "__main__":  # quick read-only summary from a terminal
    import sys

    rep = scan_safe(sys.argv[1] if len(sys.argv) > 1 else None)
    gb = lambda n: f"{n / 1024 ** 3:7.2f} GB"  # noqa: E731
    t = rep["totals"]
    print(f"{rep['root']}: {gb(t.get('bytes', 0))} in {t.get('files', 0):,} files")
    for x in rep["top"][:15]:
        print(f"  {gb(x['size'])}  {x['name']}")
    print(f"duplicates waste {gb(t.get('dupes_wasted', 0))} ({gb(t.get('dupes_outside_lab', 0))} outside lab); regenerable {gb(t.get('regen_bytes', 0))} "
          f"({gb(t.get('regen_outside_lab', 0))} outside lab); old files {gb(t.get('old_bytes', 0))}")
    for n in rep["notes"]:
        print("note:", n)
