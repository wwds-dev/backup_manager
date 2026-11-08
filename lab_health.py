"""Qt-free helpers for the Lab Health card: manifest check, ignore list, commit.

Kept out of main.py so the rules can be tested without a window.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

MANIFESTS = ("requirements.txt", "pyproject.toml", "setup.py", "Pipfile")
SKIP_DIRS = {".git", ".venv", "venv", "env", "node_modules", "__pycache__", "build", "dist",
             ".claude", "worktrees"}
GITLEAKS = shutil.which("gitleaks") or "/opt/homebrew/bin/gitleaks"


def _walk(proj: Path, max_depth: int):
    """Yield (dir, filenames) down to max_depth, skipping environments and builds."""
    base = len(proj.parts)
    for root, dirs, files in os.walk(proj):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d not in JUNK_NAMES
                   and not d.endswith(".noindex")]
        if len(Path(root).parts) - base >= max_depth:
            dirs[:] = []
        yield Path(root), files


def manifest_status(proj: Path) -> str:
    """'ok' (a manifest exists at the root or in a sub-project), 'missing' (Python
    code but no manifest anywhere), or 'n/a' (no Python code, so none is expected)."""
    proj = proj.resolve()
    has_py = False
    for root, files in _walk(proj, 3):
        if any(f in MANIFESTS for f in files):
            return "ok"
        if not has_py and any(f.endswith(".py") for f in files):
            has_py = True
    return "missing" if has_py else "n/a"


def ignore_file() -> Path:
    import cloud_quota
    return cloud_quota.SECRETS_DIR / "lab_health_ignore.json"


def load_ignored(path: Path | None = None) -> set[str]:
    try:
        return set(json.loads((path or ignore_file()).read_text()))
    except (OSError, ValueError, TypeError):
        return set()


def save_ignored(names: set[str], path: Path | None = None) -> None:
    path = path or ignore_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(names), indent=1))


def _git(proj: Path, *args: str, timeout: int = 60):
    r = subprocess.run(["git", "-C", str(proj), *args], capture_output=True, text=True,
                       timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def commit_all(proj: Path, message: str, gitleaks: str | None = None) -> tuple[bool, str]:
    """Stage everything, scan the staged changes with gitleaks, commit.

    A detected secret unstages everything and commits nothing. A missing gitleaks
    also refuses: unlike the unattended snapshot, a person is here to install it.
    """
    gitleaks = gitleaks or GITLEAKS
    proj = proj.resolve()
    message = message.strip()
    if not message:
        return False, "Empty commit message."
    if not (proj / ".git").exists():
        return False, "Not a git repo."
    if not os.path.exists(gitleaks):
        return False, "gitleaks not found; refusing to commit without a secret scan."
    rc, out = _git(proj, "add", "-A")
    if rc:
        return False, out
    r = subprocess.run([gitleaks, "git", "--staged", "--no-banner", str(proj)],
                       capture_output=True, text=True, timeout=120)
    if r.returncode:
        _git(proj, "reset", "-q")
        return False, ("gitleaks flagged a possible secret; nothing committed.\n"
                       f"See: cd {proj} && git add -A && gitleaks git --staged -v\n"
                       + (r.stdout + r.stderr).strip()[-800:])
    rc, out = _git(proj, "commit", "-m", message)
    return rc == 0, out


BIG_FILE_MB = 5
MANY_FILES = 200
MANY_DELETED = 10
_SECRET_NAMES = {"id_rsa", "id_ed25519", "id_ecdsa", "credentials", "credentials.json",
                 "secrets.json", "secrets.toml", "service-account.json", ".npmrc", ".netrc"}
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".kdbx")
_GENERATED = ("node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".pytest_cache",
              ".mypy_cache", ".ruff_cache", ".DS_Store")


def _looks_secret(name: str) -> bool:
    low = name.lower()
    if low.startswith(".env"):
        return not low.endswith((".example", ".sample", ".template"))
    return low in _SECRET_NAMES or low.endswith(_SECRET_SUFFIXES)


def commit_warnings(proj: Path) -> list[str]:
    """Reasons a blanket `git add -A && git commit` of this project may do harm.

    Empty means nothing suspicious. This is advice, not a gate: gitleaks still scans
    the content, and the person decides. Every check reads only; nothing is staged.
    """
    proj = proj.resolve()
    out: list[str] = []
    rc, gd = _git(proj, "rev-parse", "--git-dir", timeout=20)
    if rc:
        return ["Not a git repo."]
    gitdir = (proj / gd) if not os.path.isabs(gd) else Path(gd)
    for marker, what in (("MERGE_HEAD", "a merge"), ("rebase-merge", "a rebase"),
                         ("rebase-apply", "a rebase"), ("CHERRY_PICK_HEAD", "a cherry-pick")):
        if (gitdir / marker).exists():
            out.append(f"{what.capitalize()} is in progress here; committing everything "
                       "would record it half-done.")
            break
    if _git(proj, "symbolic-ref", "-q", "HEAD", timeout=20)[0]:
        out.append("Detached HEAD: the commit would belong to no branch and is easy to lose.")
    try:
        r = subprocess.run(["git", "-C", str(proj), "status", "--porcelain=v1", "-z", "-uall"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return out + ["Could not read the change list."]
    entries = [e for e in r.stdout.split("\0") if len(e) > 3]
    paths = [(e[:2], e[3:]) for e in entries]
    if len(paths) > MANY_FILES:
        out.append(f"{len(paths)} files would be committed at once; review them first.")
    deleted = [p for st, p in paths if "D" in st]
    if len(deleted) >= MANY_DELETED:
        out.append(f"{len(deleted)} tracked files were deleted; check that is intended.")
    secrets = sorted({p for _, p in paths if _looks_secret(Path(p).name)})
    if secrets:
        out.append("Looks like a secret or key file: " + ", ".join(secrets[:4])
                   + (" …" if len(secrets) > 4 else "") + ". gitleaks may not catch a whole "
                   "file; add it to .gitignore if it should stay local.")
    gen = sorted({p.split("/")[0] if p.split("/")[0] in _GENERATED else
                  next(x for x in p.split("/") if x in _GENERATED)
                  for _, p in paths if any(x in _GENERATED for x in p.split("/"))})
    if gen:
        out.append("Generated or machine-local files are not git-ignored: " + ", ".join(gen[:5])
                   + ". They would bloat the history permanently.")
    nested = sorted({p for st, p in paths if p.endswith("/")})
    if nested:
        out.append("A nested git repo would be added as an empty pointer, without its "
                   "files: " + ", ".join(nested[:3]) + ".")
    big = []
    for st, p in paths:
        if "D" in st or p.endswith("/"):
            continue
        try:
            if (proj / p).stat().st_size > BIG_FILE_MB * 1024 * 1024:
                big.append(p)
        except OSError:
            pass
    if big:
        out.append(f"Files over {BIG_FILE_MB} MB (stay in history forever): "
                   + ", ".join(big[:3]) + (" …" if len(big) > 3 else "") + ".")
    return out


def commit_targets(rows: list[dict], selected: list[int]) -> list[dict]:
    """Every selected row the Commit button can act on (a repo with changes)."""
    return [rows[i] for i in selected
            if 0 <= i < len(rows) and rows[i].get("has_git") and rows[i].get("uncommitted")
            and not rows[i].get("external")]


def is_external(link: Path, root: Path) -> bool:
    """True when a lab/active entry is a symlink or resolves outside lab/active.

    Such projects live elsewhere (another app's folder, a Codex workspace), so the
    card reports on them but never deletes anything inside them.
    """
    if link.is_symlink():
        return True
    try:
        link.resolve().relative_to(root.resolve())
        return False
    except ValueError:
        return True


def git_label(has_git: bool, uncommitted: int, last_commit: str,
              external: bool) -> tuple[str, str]:
    """(text, colour) for the Git column. A plain folder linked in from elsewhere
    is not a lab project missing its repo, so it reads neutral grey, not red."""
    if not has_git:
        return ("plain folder", "#6b7280") if external else ("no git repo", "#dc2626")
    if uncommitted:
        return f"{uncommitted} uncommitted", "#d97706"
    return f"clean ({last_commit})", "#16a34a"


# Folders the card can reclaim, split by what deleting them costs.
JUNK_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache"}
ENV_NAMES = {".venv", "venv", "env", "node_modules", "dist", "build"}
DISPOSABLE_NAMES = JUNK_NAMES | ENV_NAMES
IDLE_DAYS = 30   # an env is only offered once its project has been idle this long
_PY_ENVS = {".venv", "venv", "env"}


def rebuild_command(proj: Path, folder: Path) -> str | None:
    """How to recreate `folder`, or None when nothing in the project says how.
    A venv or node_modules without a manifest/lockfile cannot be rebuilt, so it
    is never offered for deletion."""
    here = folder.parent
    has = lambda name: (here / name).exists() or (proj / name).exists()  # noqa: E731
    if folder.name in _PY_ENVS:
        if has("uv.lock") or has("pyproject.toml"):
            return "uv sync"
        if has("requirements.txt"):
            return "pip install -r requirements.txt"
        if has("Pipfile"):
            return "pipenv install"
        if has("setup.py"):
            return "pip install -e ."
    elif folder.name == "node_modules":
        if has("package-lock.json"):
            return "npm ci"
        if has("pnpm-lock.yaml"):
            return "pnpm install --frozen-lockfile"
        if has("yarn.lock"):
            return "yarn install --frozen-lockfile"
        if has("package.json"):
            return "npm install"
    else:  # dist / build
        if has("package.json"):
            return "npm run build"
        if has("pyproject.toml"):
            return "python -m build"
        if has("Makefile"):
            return "make"
    return None


def idle_days(proj: Path, now: float | None = None) -> int | None:
    """Whole days since the project last saw activity: the newer of its last
    commit and its newest source-file edit (environments and builds ignored)."""
    import time
    now = time.time() if now is None else now
    newest = 0.0
    if (proj / ".git").exists():
        try:
            rc, out = _git(proj, "log", "-1", "--format=%ct", timeout=20)
            if rc == 0 and out.strip().isdigit():
                newest = float(out.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    for root, files in _walk(proj, 4):
        for f in files:
            if f == ".DS_Store":   # Finder touches it just by opening the folder
                continue
            try:
                newest = max(newest, (root / f).stat().st_mtime)
            except OSError:
                pass
    return None if newest == 0.0 else max(0, int((now - newest) // 86400))


# --- Per-environment use ---------------------------------------------------------
# A .venv / node_modules is judged by its own last use, not its project's: an env
# untouched for ENV_IDLE_DAYS that nothing runs from is offered even in an active
# project. dist/build keep the project-idle rule (IDLE_DAYS).
ENV_IDLE_DAYS = 7
_USE_ENVS = _PY_ENVS | {"node_modules"}
LAUNCHD_DIRS = (Path.home() / "Library/LaunchAgents", Path("/Library/LaunchAgents"),
                Path("/Library/LaunchDaemons"))
APPS_DIR = Path("/Applications")


def _days(n: int) -> str:
    return f"{n} day{'s' if n != 1 else ''}"


def env_last_use(env: Path) -> float | None:
    """Newest mtime of what changes when an env is installed into or used to
    install: its bin/ entries and pyvenv.cfg (Python), or .bin/ and the npm/pnpm
    state files (node_modules). None when none of them exist."""
    probes = [env / "bin", env / "pyvenv.cfg", env / ".bin", env / ".package-lock.json",
              env / ".modules.yaml", env / ".yarn-integrity"]
    newest = 0.0
    for p in probes:
        try:
            newest = max(newest, p.lstat().st_mtime)
            if p.is_dir() and not p.is_symlink():
                for e in os.scandir(p):
                    newest = max(newest, e.stat(follow_symlinks=False).st_mtime)
        except OSError:
            pass
    return newest or None


def process_snapshot() -> list[tuple[int, str, str]]:
    """(pid, name, path) for every running process: its command line (ps) and every
    executable or library it has mapped (lsof txt), so a Python started as plain
    `python` still shows up through the site-packages modules it loaded."""
    out: list[tuple[int, str, str]] = []
    try:
        r = subprocess.run(["ps", "-axww", "-o", "pid=,command="],
                           capture_output=True, text=True, timeout=20)
        for line in r.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[0].isdigit():
                out.append((int(parts[0]), Path(parts[1].split()[0]).name, parts[1]))
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        r = subprocess.run(["lsof", "-n", "-w", "-d", "txt", "-Fpcn"],
                           capture_output=True, text=True, timeout=30)
        pid, name = 0, ""
        for line in r.stdout.splitlines():
            tag, val = line[:1], line[1:]
            if tag == "p":
                pid = int(val) if val.isdigit() else 0
            elif tag == "c":
                name = val
            elif tag == "n" and pid:
                out.append((pid, name, val))
    except (OSError, subprocess.SubprocessError):
        pass
    return out


def _plist_strings(path: Path) -> list[str]:
    import plistlib
    try:
        data = plistlib.loads(path.read_bytes())
    except Exception:
        try:
            return [path.read_text(errors="ignore")]
        except OSError:
            return []
    found: list[str] = []

    def walk(v):
        if isinstance(v, str):
            found.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
    walk(data)
    return found


def launchd_jobs(dirs=LAUNCHD_DIRS) -> dict[str, list[str]]:
    """plist file name -> every string in it (program, arguments, working dir)."""
    jobs = {}
    for d in dirs:
        try:
            for p in sorted(Path(d).glob("*.plist")):
                jobs[p.name] = _plist_strings(p)
        except OSError:
            pass
    return jobs


def app_project_roots(apps_dir: Path = APPS_DIR) -> dict[str, str]:
    """App name -> the checkout it runs from, from Contents/Resources/project_root.txt
    (Lab Hub-built apps launch the checkout's .venv)."""
    roots = {}
    for rec in sorted(Path(apps_dir).glob("*.app/Contents/Resources/project_root.txt")):
        try:
            text = rec.read_text().strip()
        except OSError:
            continue
        if text:
            roots[rec.parents[2].stem] = os.path.realpath(os.path.expanduser(text))
    return roots


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def env_users(env: Path, proj: Path, procs=(), jobs=None, apps=None) -> list[str]:
    """Everything that still runs from `env`: live processes with a path inside it,
    launchd jobs naming it, apps whose project_root.txt points at its checkout.
    A launchd job that runs a script from the checkout also counts for the
    checkout's own Python env, since that script most likely uses it."""
    env_s, env_r = str(env), os.path.realpath(env)
    roots = {env_s, env_r}
    proj_r = os.path.realpath(proj)
    own_py = env.name in _PY_ENVS and os.path.realpath(env.parent) == proj_r
    users: list[str] = []
    seen = set()
    for pid, name, path in procs:
        if pid in seen:
            continue
        if any(_inside(path, r) or f"{r.rstrip('/')}/" in path for r in roots):
            seen.add(pid)
            users.append(f"running process {name or '?'} (pid {pid})")
    for job, strings in (jobs or {}).items():
        if any(_inside(s, r) or f"{r.rstrip('/')}/" in s for s in strings for r in roots):
            users.append(f"launchd job {job}")
        elif own_py and any(_inside(s, proj_r) and s != proj_r for s in strings):
            users.append(f"launchd job {job} (runs from this project)")
    if env.name in _PY_ENVS:
        for app, root in (apps or {}).items():
            if root == os.path.realpath(env.parent):
                users.append(f"{app}.app (launches from this checkout)")
    return users


def _manifest_lines(proj: Path, folder: Path) -> tuple[str, list[str]] | None:
    names = (("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "package.json")
             if folder.name == "node_modules" else ("uv.lock", "requirements.txt"))
    for name in names:
        for base in (folder.parent, proj):
            try:
                text = (base / name).read_text(errors="ignore")
            except OSError:
                continue
            lines = [l.strip() for l in text.splitlines()]
            return name, sorted(l for l in lines if l and not l.startswith("#"))
    return None


def manifest_hash(proj: Path, folder: Path) -> str | None:
    """Hash of the lockfile/manifest a .venv / node_modules was built from (uv.lock,
    else requirements.txt; package-lock.json etc. for node_modules), or None."""
    import hashlib
    if folder.name not in _USE_ENVS or not (found := _manifest_lines(proj, folder)):
        return None
    name, lines = found
    return f"{name}:{hashlib.sha256(chr(10).join(lines).encode()).hexdigest()[:16]}"


def package_set_hash(proj: Path, folder: Path) -> str | None:
    """Hash of just the package names in requirements.txt (pins ignored), so two
    envs of the same project family that drifted a few versions apart still match."""
    import hashlib
    import re
    found = _manifest_lines(proj, folder) if folder.name in _PY_ENVS else None
    if not found or found[0] != "requirements.txt":
        return None
    pkgs = sorted({re.split(r"[\s=<>!~;\[@]", l, maxsplit=1)[0].lower().replace("_", "-")
                   for l in found[1] if not l.startswith("-")} - {""})
    return "pkgs:" + hashlib.sha256("\n".join(pkgs).encode()).hexdigest()[:16] if pkgs else None


def mark_duplicates(rows: list[dict]) -> None:
    """Group envs built from the same manifest (`manifest_hash`), or failing that from
    the same package list with other pins (`package_set_hash`). Each grouped env gets
    `duplicates` (the other paths), `dup_kind`, and `oldest` (True for the least
    recently used offered env of its group: the obvious one to remove)."""
    envs = [it for row in rows for it in row.get("items", []) if it.get("kind") == "env"]
    for key, kind in (("manifest_hash", "same manifest"),
                      ("package_set_hash", "same packages, other versions")):
        groups: dict[str, list[dict]] = {}
        for it in envs:
            if it.get(key) and "duplicates" not in it:
                groups.setdefault(it[key], []).append(it)
        for group in groups.values():
            if len(group) < 2:
                continue
            group.sort(key=lambda i: i.get("last_use") or 0)
            free = [i for i in group if i.get("eligible")]   # never point at a locked env
            for it in group:
                it["duplicates"] = [str(o["path"]) for o in group if o is not it]
                it["dup_kind"] = kind
                it["oldest"] = bool(free) and it is free[0]


def classify_item(proj: Path, folder: Path, kb: int, idle: int | None,
                  users: list[str] | None = None, last_use: float | None = None,
                  now: float | None = None) -> dict:
    """One reclaimable folder with what it costs to delete and whether it is offered.
    kind 'junk' regenerates by itself; kind 'env' needs a rebuild, so it is offered
    only when it can be rebuilt, nothing uses it, and it is idle: a .venv /
    node_modules by its own last use (ENV_IDLE_DAYS), dist/build by the project's
    (IDLE_DAYS)."""
    import time
    now = time.time() if now is None else now
    item = {"path": folder, "kb": kb, "kind": "junk", "rebuild": None,
            "eligible": True, "reason": "", "users": list(users or []),
            "last_use": last_use}
    if folder.name in JUNK_NAMES:
        return item
    item["kind"] = "env"
    item["rebuild"] = rebuild_command(proj, folder)
    if item["rebuild"] is None:
        item["eligible"] = False
        item["reason"] = "no lockfile or manifest, so it could not be rebuilt"
    elif item["users"]:
        item["eligible"] = False
        item["reason"] = "in use: " + "; ".join(item["users"])
    elif folder.name in _USE_ENVS:
        if last_use is None:
            item["eligible"] = False
            item["reason"] = "last use unknown"
        else:
            used = max(0, int((now - last_use) // 86400))
            if used < ENV_IDLE_DAYS:
                item["eligible"] = False
                item["reason"] = (f"used {_days(used)} ago "
                                  f"(offered after {ENV_IDLE_DAYS} unused)")
    elif idle is None or idle < IDLE_DAYS:
        item["eligible"] = False
        item["reason"] = ("activity unknown" if idle is None
                          else f"project active {_days(idle)} ago "
                               f"(offered after {IDLE_DAYS})")
    return item


def env_tooltip_line(item: dict, size: str, now: float | None = None) -> str:
    """One Envs-cell tooltip entry: size, last use, what uses it, how to rebuild,
    and any duplicate built from the same manifest."""
    import time
    now = time.time() if now is None else now
    parts = [f"{item['path'].name} ({size})"]
    if item.get("last_use"):
        parts.append(f"last used {_days(max(0, int((now - item['last_use']) // 86400)))} ago")
    if not item.get("eligible"):
        parts.append(f"not offered: {item.get('reason')}")
    elif item.get("kind") == "env":
        parts.append("nothing uses it; moved to Trash")
    lines = [", ".join(parts)]
    if item.get("rebuild"):
        lines.append(f"   rebuild: {item['rebuild']}")
    if item.get("duplicates"):
        lines.append(f"   {item.get('dup_kind', 'same manifest')} as: "
                     + ", ".join(item["duplicates"])
                     + ("  ← oldest copy, remove this one" if item.get("oldest") else ""))
    return "\n".join(lines)


def cleanup_targets(rows: list[dict], junk_rows: set[int],
                    env_rows: set[int]) -> list[dict]:
    """Folders to delete for the ticked rows: caches from `junk_rows`, environments
    from `env_rows`. Linked projects are skipped, an environment that is not
    eligible is never returned, and every path must sit inside its project,
    whatever the UI shows."""
    targets = []
    for i in sorted(junk_rows | env_rows):
        if i >= len(rows) or rows[i].get("external"):
            continue
        row = rows[i]
        base = Path(row["path"]).resolve()
        for item in row["items"]:
            if item["kind"] == "junk" and i not in junk_rows:
                continue
            if item["kind"] == "env" and (i not in env_rows or not item["eligible"]):
                continue
            p = Path(item["path"])
            if p.is_symlink():
                continue
            try:
                p.resolve().relative_to(base)
            except ValueError:
                continue
            if p.resolve() != base:
                targets.append({**item, "project": row["name"], "path": p})
    return targets


def commit_target(rows: list[dict], selected: list[int]) -> dict | None:
    """The row the Commit button acts on: exactly one selected row with changes."""
    if len(selected) != 1 or not 0 <= selected[0] < len(rows):
        return None
    row = rows[selected[0]]
    return row if row.get("has_git") and row.get("uncommitted") else None


# --- Thresholds the person can change --------------------------------------------

def settings_file() -> Path:
    import cloud_quota
    return cloud_quota.SECRETS_DIR / "lab_health_settings.json"


def load_settings(path: Path | None = None) -> dict:
    """{'env_idle_days': int, 'project_idle_days': int}, defaults where unset or invalid."""
    out = {"env_idle_days": ENV_IDLE_DAYS, "project_idle_days": IDLE_DAYS}
    try:
        data = json.loads((path or settings_file()).read_text())
    except (OSError, ValueError, TypeError):
        return out
    if isinstance(data, dict):
        for k in out:
            v = data.get(k)
            if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 365:
                out[k] = v
    return out


def save_settings(settings: dict, path: Path | None = None) -> None:
    path = path or settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {k: int(settings[k]) for k in ("env_idle_days", "project_idle_days")}, indent=1))


def apply_settings(settings: dict) -> None:
    """Make the thresholds in `settings` the ones classify_item() uses."""
    global ENV_IDLE_DAYS, IDLE_DAYS
    ENV_IDLE_DAYS = int(settings["env_idle_days"])
    IDLE_DAYS = int(settings["project_idle_days"])


# --- Where the space is ----------------------------------------------------------

def _du_kb(path: Path, timeout: int = 120) -> int:
    try:
        r = subprocess.run(["du", "-sk", str(path)], capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return 0
    head = r.stdout.split("\t", 1)[0].strip()
    return int(head) if head.isdigit() else 0


def top_folders(proj: Path, n: int = 10, min_kb: int = 1024) -> list[tuple[int, Path]]:
    """The n biggest folders up to two levels below `proj` (largest first, nested
    entries included so .git or data/models stand out), ignoring those under min_kb."""
    proj = proj.resolve()
    try:
        r = subprocess.run(["du", "-k", "-d", "2", str(proj)], capture_output=True,
                           text=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in r.stdout.splitlines():
        kb, _, path = line.partition("\t")
        if kb.isdigit() and path and Path(path) != proj and int(kb) >= min_kb:
            found.append((int(kb), Path(path)))
    found.sort(key=lambda t: -t[0])
    return found[:n]


def system_cache_locations(home: Path | None = None) -> list[dict]:
    """Well-known tool caches outside lab/active that regenerate on demand. Reported
    with the tool's own cleanup command; this card never deletes them."""
    home = home or Path.home()
    lib = home / "Library"
    spec = [
        ("pip", lib / "Caches" / "pip", "pip cache purge"),
        ("uv", home / ".cache" / "uv", "uv cache clean"),
        ("uv (Library)", lib / "Caches" / "uv", "uv cache clean"),
        ("Homebrew downloads", lib / "Caches" / "Homebrew", "brew cleanup --prune=all"),
        ("npm", home / ".npm" / "_cacache", "npm cache clean --force"),
        ("pnpm store", lib / "pnpm", "pnpm store prune"),
        ("Yarn", lib / "Caches" / "Yarn", "yarn cache clean"),
        ("Xcode DerivedData", lib / "Developer" / "Xcode" / "DerivedData",
         "rm -rf ~/Library/Developer/Xcode/DerivedData/*"),
        ("Unavailable simulators", lib / "Developer" / "CoreSimulator",
         "xcrun simctl delete unavailable"),
        ("Hugging Face models", home / ".cache" / "huggingface",
         "huggingface-cli delete-cache   (models re-download when used)"),
        ("PyTorch models", home / ".cache" / "torch", "rm -rf ~/.cache/torch   (re-downloads)"),
        ("Docker data", lib / "Containers" / "com.docker.docker", "docker system prune -a"),
    ]
    out = []
    for label, path, cmd in spec:
        if path.exists():
            out.append({"label": label, "path": path, "kb": _du_kb(path), "cmd": cmd})
    out.sort(key=lambda d: -d["kb"])
    return out
