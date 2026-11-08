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
    """Every selected row the Commit button can act on (a repo with changes).
    Linked projects count too; their commit dialog carries linked_warning()."""
    return [rows[i] for i in selected
            if 0 <= i < len(rows) and rows[i].get("has_git") and rows[i].get("uncommitted")]


def linked_warning(path: str | Path) -> str:
    """The commit warning every linked (symlinked / outside lab/active) project gets."""
    return (f"Linked project: it lives at {path}, outside lab/active. If another tool or "
            "session is working there, its unfinished changes would be committed too.")


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
    `python` still shows up through the site-packages modules it loaded. The
    scanning process itself is left out, so a scan run from an env never locks it."""
    out: list[tuple[int, str, str]] = []
    me = os.getpid()
    try:
        r = subprocess.run(["ps", "-axww", "-o", "pid=,command="],
                           capture_output=True, text=True, timeout=20)
        for line in r.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[0].isdigit() and int(parts[0]) != me:
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
            elif tag == "n" and pid and pid != me:
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


LAB_HUB_APPS_TOML = Path("lab_hub") / "lab_hub" / "apps.toml"


def lab_hub_apps(lab_active: Path) -> list[dict]:
    """Apps Lab Hub launches, from <lab/active>/lab_hub/lab_hub/apps.toml:
    {key, name, project (real path), from_source}. A from-source app runs
    `<project>/.venv/bin/python <entry>`, so that env must never be offered."""
    import tomllib
    try:
        data = tomllib.loads((Path(lab_active) / LAB_HUB_APPS_TOML).read_text())
    except (OSError, ValueError):
        return []
    apps = []
    for group in data.values():
        if not isinstance(group, list):
            continue
        for a in group:
            if isinstance(a, dict) and a.get("project"):
                apps.append({"key": str(a.get("key", "")), "name": str(a.get("name", a["project"])),
                             "project": os.path.realpath(Path(lab_active) / str(a["project"])),
                             "from_source": a.get("runs_from_source", True) is not False})
    return apps


def bundle_references(apps_dir: Path = APPS_DIR, max_kb: int = 256) -> dict[str, list[str]]:
    """App name -> absolute paths named in its launcher scripts, Info.plist and small
    text resources (Contents/MacOS/*, Contents/Resources/*), so a bundle whose stub
    runs `<checkout>/.venv/bin/python` is seen even without project_root.txt."""
    import re
    pat = re.compile(rb"(/Users/[^\s\"'<>:;,]+)")
    refs: dict[str, list[str]] = {}
    for app in sorted(Path(apps_dir).glob("*.app")):
        found: set[str] = set()
        files = [app / "Contents" / "Info.plist"]
        for sub in ("MacOS", "Resources"):
            try:
                files += [p for p in (app / "Contents" / sub).iterdir() if p.is_file()]
            except OSError:
                pass
        for f in files:
            try:
                if f.stat().st_size > max_kb * 1024:
                    continue
                found.update(m.decode(errors="ignore").rstrip("/.")
                             for m in pat.findall(f.read_bytes()))
            except OSError:
                continue
        if found:
            refs[app.stem] = sorted(found)
    return refs


def self_env_paths() -> list[str]:
    """Where the running interpreter lives (the app's own env when run from source)."""
    import sys
    return sorted({os.path.realpath(sys.prefix),
                   os.path.realpath(Path(sys.executable).parent.parent)})


def usage_snapshot(lab_active: Path) -> dict:
    """Everything env_users() / use_evidence() look at, gathered once per scan."""
    return {"procs": process_snapshot(), "jobs": launchd_jobs(),
            "apps": app_project_roots(), "bundles": bundle_references(),
            "hub": lab_hub_apps(lab_active), "self": self_env_paths(),
            "hub_logs": lab_hub_launch_times(lab_hub_apps(lab_active)),
            "history": shell_history()}


def env_users(env: Path, proj: Path, procs=(), jobs=None, apps=None, *, hub=(),
              bundles=None, self_paths=()) -> list[str]:
    """Everything that still runs from `env`, idle or not: this app itself, live
    processes with a path inside it, launchd jobs naming it, Lab Hub apps run from
    its checkout, installed bundles whose project_root.txt or launcher names it.
    A launchd job or bundle that runs something from the checkout also counts for
    the checkout's own root env, since that is the env it most likely uses."""
    env_s, env_r = str(env), os.path.realpath(env)
    roots = {env_s, env_r}
    proj_r = os.path.realpath(proj)
    base_r = os.path.realpath(env.parent)
    own_py = env.name in _USE_ENVS and base_r == proj_r
    users: list[str] = []
    for sp in self_paths:
        if _inside(sp, env_r):
            users.append("this app (Backup Control Center) runs from it")
    for h in hub:
        if h["from_source"] and h["project"] == base_r and env.name in _USE_ENVS:
            users.append(f"Lab Hub app {h['name']} runs from this checkout")
    for app, paths in (bundles or {}).items():
        if any(_inside(p, r) for p in paths for r in roots):
            users.append(f"{app}.app names it in its launcher")
        elif own_py and app not in (apps or {}) and any(
                _inside(p, proj_r) and p != proj_r for p in paths):
            users.append(f"{app}.app launches from this checkout")
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
    if env.name in _USE_ENVS:
        for app, root in (apps or {}).items():
            if root == base_r:
                users.append(f"{app}.app (launches from this checkout)")
    return users


# --- Evidence an env was used recently --------------------------------------------
# Running code leaves no trace in the env itself (bin/ changes only on install and
# macOS stops updating read times after the first read), so look at what running
# the project writes next to it.
_EVIDENCE_SKIP = SKIP_DIRS | {"node_modules", ".claude", "worktrees"}
HISTORY_FILES = (Path.home() / ".zsh_history", Path.home() / ".bash_history")
HISTORY_RECENT_LINES = 300   # untimestamped history: only the tail counts, dated by mtime


def _newest(paths) -> float:
    newest = 0.0
    for p in paths:
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            pass
    return newest


def _newest_tree(root: Path, max_files: int = 2000) -> float:
    newest, n = 0.0, 0
    for r, _, files in os.walk(root):
        for f in files:
            n += 1
            try:
                newest = max(newest, os.stat(os.path.join(r, f)).st_mtime)
            except OSError:
                pass
            if n >= max_files:
                return newest
    return newest


def lab_hub_launch_times(hub: list[dict], log_dir: Path | None = None) -> dict[str, float]:
    """Project real path -> when Lab Hub last launched it (its launch log's mtime)."""
    import tempfile
    log_dir = Path(log_dir or tempfile.gettempdir())
    out = {}
    for h in hub:
        t = _newest([log_dir / f"lab-hub-launch-{h['key']}.log"])
        if t:
            out[h["project"]] = max(out.get(h["project"], 0.0), t)
    return out


def shell_history(files=HISTORY_FILES) -> list[tuple[float, str]]:
    """(time, command) for recent shell commands. zsh extended entries carry their
    own time; plain entries count only in the last HISTORY_RECENT_LINES lines and
    are dated by the history file's mtime (so: "recently", not exactly when)."""
    out = []
    for f in files:
        try:
            mtime = f.stat().st_mtime
            lines = f.read_bytes().decode(errors="ignore").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            if line.startswith(": ") and ";" in line:
                stamp = line[2:].split(":", 1)[0]
                if stamp.isdigit():
                    out.append((float(stamp), line.split(";", 1)[1]))
                    continue
            if i >= len(lines) - HISTORY_RECENT_LINES:
                out.append((mtime, line))
    return out


def use_evidence(env: Path, usage: dict | None = None) -> list[tuple[float, str]]:
    """(time, what) signs that the checkout owning `env` was run recently, newest
    first: bytecode compiled from its sources, tests run, logs written, uv.lock
    touched, a dev-server cache, a Lab Hub launch, shell history naming it."""
    import re
    usage = usage or {}
    base = env.parent
    ev: list[tuple[float, str]] = []
    py = env.name in _PY_ENVS
    if py:
        pyc = 0.0
        depth0 = len(base.parts)
        for r, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in _EVIDENCE_SKIP - {"__pycache__"}
                       and not d.endswith(".noindex")]
            if len(Path(r).parts) - depth0 >= 5:
                dirs[:] = []
            if Path(r).name == "__pycache__":
                pyc = max(pyc, _newest(Path(r) / f for f in files if f.endswith(".pyc")))
        if pyc:
            ev.append((pyc, "Python bytecode compiled from its sources"))
        t = _newest([base / "uv.lock"])
        if t:
            ev.append((t, "uv.lock updated"))
    if (base / ".pytest_cache").is_dir():
        t = _newest_tree(base / ".pytest_cache")
        if t:
            ev.append((t, "tests run (.pytest_cache)"))
    logs = [p for d in (base, base / "logs", base / "log")
            for p in (d.glob("*.log") if d.is_dir() else [])]
    t = _newest(logs)
    if t:
        ev.append((t, "log file written"))
    if env.name == "node_modules":
        t = _newest([env / ".vite", env / ".cache", base / ".next", base / ".vite",
                     base / ".turbo"])
        if t:
            ev.append((t, "dev-server / build cache"))
    base_r = os.path.realpath(base)
    t = (usage.get("hub_logs") or {}).get(base_r)
    if t:
        ev.append((t, "launched from Lab Hub"))
    name = re.escape(base.name)
    cd = re.compile(rf"(^|[\s;&|])cd\s+(\S*/)?{name}/?($|[\s;&|])")
    hist = [ts for ts, cmd in usage.get("history") or ()
            if base_r in cmd or str(base) in cmd or cd.search(cmd)]
    if hist:
        ev.append((max(hist), "named in shell history"))
    return sorted(ev, reverse=True)


def use_memory_file() -> Path:
    import cloud_quota
    return cloud_quota.SECRETS_DIR / "env_last_use.json"


def load_use_memory(path: Path | None = None) -> dict:
    try:
        mem = json.loads((path or use_memory_file()).read_text())
        return mem if isinstance(mem, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_use_memory(mem: dict, path: Path | None = None) -> None:
    path = path or use_memory_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(mem, indent=1))
    except OSError:
        pass


def recall_use(env: Path, evidence: list[tuple[float, str]],
               mem: dict) -> list[tuple[float, str]]:
    """`evidence` plus the newest sign of use remembered from earlier scans, and
    `mem` updated with today's newest. Cleaning caches deletes the .pyc and
    .pytest_cache evidence, so without this an env would look idle on the very
    next scan."""
    key = os.path.realpath(env)
    ev = list(evidence)
    old = mem.get(key)
    if isinstance(old, list) and len(old) == 2 and isinstance(old[0], (int, float)):
        ev.append((float(old[0]), f"{old[1]} (seen on an earlier scan)"))
    ev.sort(reverse=True)
    if ev:
        mem[key] = [ev[0][0], ev[0][1].replace(" (seen on an earlier scan)", "")]
    return ev


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
                  now: float | None = None,
                  evidence: list[tuple[float, str]] | None = None) -> dict:
    """One reclaimable folder with what it costs to delete and whether it is offered.
    kind 'junk' regenerates by itself; kind 'env' needs a rebuild, so it is offered
    only when it can be rebuilt, nothing uses it, and it is idle: a .venv /
    node_modules when its newest sign of use (installs into it, `evidence` from
    use_evidence(), and for the project's root env the project's own last edit)
    is ENV_IDLE_DAYS old; dist/build by the project's idle time (IDLE_DAYS)."""
    import time
    now = time.time() if now is None else now
    signs = list(evidence or [])
    if last_use:
        signs.append((last_use, "packages installed or updated in it"))
    if (folder.name in _USE_ENVS and idle is not None
            and os.path.realpath(folder.parent) == os.path.realpath(proj)):
        signs.append((now - idle * 86400, "project files edited or committed"))
    signs.sort(reverse=True)
    item = {"path": folder, "kb": kb, "kind": "junk", "rebuild": None,
            "eligible": True, "reason": "", "users": list(users or []),
            "last_use": signs[0][0] if signs else None,
            "last_use_source": signs[0][1] if signs else "", "evidence": signs}
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
        if not signs:
            item["eligible"] = False
            item["reason"] = "last use unknown"
        else:
            used = max(0, int((now - signs[0][0]) // 86400))
            if used < ENV_IDLE_DAYS:
                item["eligible"] = False
                item["reason"] = (f"used {_days(used)} ago: {signs[0][1]} "
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
        parts.append(f"last used {_days(max(0, int((now - item['last_use']) // 86400)))} ago"
                     + (f" ({item['last_use_source']})" if item.get("last_use_source") else ""))
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


def env_confirm_line(t: dict, size: str, now: float | None = None) -> str:
    """One env in the Clean up confirmation: where, last-use evidence, rebuild cost."""
    import time
    now = time.time() if now is None else now
    rel = os.path.relpath(t["path"], Path(t["path"]).parent.parent) \
        if "worktrees" in Path(t["path"]).parts else Path(t["path"]).name
    if t.get("last_use"):
        used = (f"last used {_days(max(0, int((now - t['last_use']) // 86400)))} ago"
                + (f" ({t['last_use_source']})" if t.get("last_use_source") else ""))
    else:
        used = "no sign of use found"
    return (f"  {t.get('project', '')}/{rel} ({size}): {used}\n"
            f"      rebuild: {t.get('rebuild')}, re-downloads about {size}")


# --- Rebuild records: every trashed env can be recreated --------------------------

def records_dir() -> Path:
    import cloud_quota
    return cloud_quota.SECRETS_DIR / "env_records"


def _uv() -> str | None:
    for d in ("/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin", "~/.cargo/bin"):
        p = Path(os.path.expanduser(d)) / "uv"
        if p.exists():
            return str(p)
    return shutil.which("uv")


def _python_version(env: Path) -> str | None:
    """major.minor from pyvenv.cfg (version_info, or version for older venvs)."""
    try:
        cfg = dict(l.split("=", 1) for l in (env / "pyvenv.cfg").read_text().splitlines()
                   if "=" in l)
    except OSError:
        return None
    v = {k.strip(): v.strip() for k, v in cfg.items()}
    ver = v.get("version_info") or v.get("version")
    return ".".join(ver.split(".")[:2]) if ver else None


def freeze_env(env: Path, runner=subprocess.run) -> tuple[list[str] | None, str]:
    """Exact package list of a Python env (`uv pip freeze`, else `pip freeze`)."""
    py = env / "bin" / "python"
    cmds = []
    if uv := _uv():
        cmds.append([uv, "pip", "freeze", "--python", str(py)])
    cmds.append([str(py), "-m", "pip", "freeze", "--all"])
    err = "no python in the env"
    for cmd in cmds:
        try:
            r = runner(cmd, capture_output=True, text=True, timeout=90)
        except (OSError, subprocess.SubprocessError) as e:
            err = str(e)
            continue
        if r.returncode == 0:
            return [l for l in r.stdout.splitlines() if l.strip()], ""
        err = (r.stderr or r.stdout).strip()[-300:]
    return None, err


def write_rebuild_record(target: dict, project_path: Path, out_dir: Path | None = None,
                         runner=subprocess.run, now: float | None = None) -> Path:
    """Save how to recreate an env before it goes to the Trash. Raises OSError when
    the record cannot be written; the caller must then not trash the env."""
    import time
    now = time.time() if now is None else now
    env = Path(target["path"])
    kind = ("python" if env.name in _PY_ENVS else
            "node" if env.name == "node_modules" else "other")
    rec = {"project": target.get("project", ""), "project_path": str(project_path),
           "env_path": str(env), "kind": kind, "rebuild": target.get("rebuild"),
           "kb": target.get("kb", 0), "created": now, "python": None, "freeze": None,
           "freeze_error": "", "last_use": target.get("last_use"),
           "last_use_source": target.get("last_use_source", ""), "rebuilt_at": None,
           "failed": ""}
    if kind == "python":
        rec["python"] = _python_version(env)
        rec["freeze"], rec["freeze_error"] = freeze_env(env, runner)
    out_dir = Path(out_dir or records_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    rel = os.path.relpath(env, project_path).replace("/", "_")
    path = out_dir / f"{rec['project'] or Path(project_path).name}__{rel}__{int(now)}.json"
    path.write_text(json.dumps(rec, indent=1))
    return path


def record_lost_env(project: str, project_path: Path, env: Path, kb: int = 0,
                    python: str | None = None, out_dir: Path | None = None,
                    now: float | None = None, note: str = "") -> Path:
    """A rebuild record for an env that is already gone (trashed before records
    existed). No freeze is possible, so it rebuilds from the project's lockfile or
    manifest. Refuses (ValueError) when the env still exists or nothing says how."""
    import time
    now = time.time() if now is None else now
    env, project_path = Path(env), Path(project_path)
    if env.exists():
        raise ValueError(f"{env} still exists")
    rebuild = rebuild_command(project_path, env)
    if rebuild is None:
        raise ValueError(f"no lockfile or manifest for {env}")
    kind = "python" if env.name in _PY_ENVS else "node" if env.name == "node_modules" else "other"
    rec = {"project": project, "project_path": str(project_path), "env_path": str(env),
           "kind": kind, "rebuild": rebuild, "kb": kb, "created": now,
           "python": python if kind == "python" else None, "freeze": None,
           "freeze_error": note or "env was gone before a record could be taken",
           "last_use": None, "last_use_source": "", "rebuilt_at": None, "failed": ""}
    out_dir = Path(out_dir or records_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    rel = os.path.relpath(env, project_path).replace("/", "_")
    path = out_dir / f"{project}__{rel}__{int(now)}.json"
    path.write_text(json.dumps(rec, indent=1))
    return path


def missing_env_records(out_dir: Path | None = None) -> list[dict]:
    """The newest record per env path whose env is gone (or whose last rebuild
    failed), each with `_file` set to where it is stored."""
    out_dir = Path(out_dir or records_dir())
    newest: dict[str, dict] = {}
    for f in sorted(out_dir.glob("*.json")) if out_dir.is_dir() else []:
        try:
            rec = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict) or "env_path" not in rec:
            continue
        rec["_file"] = str(f)
        old = newest.get(rec["env_path"])
        if old is None or rec.get("created", 0) >= old.get("created", 0):
            newest[rec["env_path"]] = rec
    return [r for r in newest.values()
            if not Path(r["env_path"]).exists() or r.get("failed")]


def _split_freeze(lines: list[str]) -> tuple[list[str], bool]:
    """Pinned lines safe to reinstall, and whether an editable/local install of the
    project itself was dropped (reinstalled from the checkout instead)."""
    keep, local = [], False
    for l in lines:
        s = l.strip()
        if s.startswith("-e ") or " @ file://" in s or s.startswith("file://"):
            local = True
        elif s and not s.startswith("#"):
            keep.append(s)
    return keep, local


def rebuild_plan(rec: dict) -> list[tuple[list[str], str, dict]]:
    """The commands (argv, cwd, extra env) that recreate the env in `rec`, exact
    versions when a freeze was recorded, else the project's rebuild command."""
    import shlex
    env = rec["env_path"]
    base = str(Path(env).parent)
    if rec["kind"] == "node":
        return [(shlex.split(rec["rebuild"] or "npm install"), base, {})]
    if rec["kind"] != "python":
        return [(shlex.split(rec["rebuild"]), base, {})] if rec.get("rebuild") else []
    uv = _uv()
    py = str(Path(env) / "bin" / "python")
    ver = rec.get("python")
    steps = []
    if uv:
        steps.append(([uv, "venv", "--allow-existing", *(["--python", ver] if ver else []), env],
                      base, {}))
        pip = [uv, "pip", "install", "--python", py]
    else:
        steps.append(([f"python{ver}" if ver else "python3", "-m", "venv", env], base, {}))
        pip = [py, "-m", "pip", "install"]
    if rec.get("freeze"):
        pinned, local = _split_freeze(rec["freeze"])
        if pinned:
            steps.append(([*pip, "-r", "{freeze_file}"], base, {}))
        if local and any((Path(base) / m).exists() for m in ("pyproject.toml", "setup.py")):
            steps.append(([*pip, "--no-deps", "-e", base], base, {}))
        return steps
    cmd = rec.get("rebuild") or ""
    if cmd == "uv sync" and uv:
        steps.append(([uv, "sync"], base, {"UV_PROJECT_ENVIRONMENT": env}))
    elif cmd.startswith("pip install"):
        steps.append(([*pip, *shlex.split(cmd)[2:]], base, {}))
    elif cmd:
        steps.append((shlex.split(cmd), base, {}))
    return steps


def rebuild_from_record(rec: dict, runner=subprocess.run,
                        now: float | None = None) -> tuple[bool, str]:
    """Recreate one env from its record. Never deletes anything: a failed attempt
    is left in place, marked failed, and the next attempt builds over it."""
    import tempfile
    import time
    now = time.time() if now is None else now
    env = Path(rec["env_path"])
    if not Path(rec["project_path"]).is_dir():
        return False, "project folder is gone"
    if env.exists() and not rec.get("failed"):
        return True, "already present"
    steps = rebuild_plan(rec)
    if not steps:
        return False, "no rebuild command recorded"
    freeze_file = None
    if rec.get("freeze"):
        pinned, _ = _split_freeze(rec["freeze"])
        fd, freeze_file = tempfile.mkstemp(prefix="env-freeze-", suffix=".txt")
        with os.fdopen(fd, "w") as fh:
            fh.write("\n".join(pinned) + "\n")
    ok, msg = True, ("exact versions" if rec.get("freeze") else f"ran {rec.get('rebuild')}")
    try:
        for argv, cwd, extra in steps:
            argv = [freeze_file if a == "{freeze_file}" else a for a in argv]
            try:
                r = runner(argv, cwd=cwd, capture_output=True, text=True, timeout=1800,
                           env={**os.environ, "PATH": os.environ.get("PATH", "") +
                                ":/opt/homebrew/bin:/usr/local/bin", **extra})
            except (OSError, subprocess.SubprocessError) as e:
                ok, msg = False, f"{Path(argv[0]).name}: {e}"
                break
            if r.returncode:
                ok, msg = False, (f"{Path(argv[0]).name} {' '.join(argv[1:3])}: "
                                  + (r.stderr or r.stdout).strip()[-300:])
                break
    finally:
        if freeze_file:
            try:
                os.unlink(freeze_file)
            except OSError:
                pass
    rec["failed"] = "" if ok else msg
    rec["rebuilt_at"] = now if ok else None
    if rec.get("_file"):
        try:
            Path(rec["_file"]).write_text(json.dumps(
                {k: v for k, v in rec.items() if k != "_file"}, indent=1))
        except OSError:
            pass
    return ok, msg


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


TOOL_PATHS = ("/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin", "~/.cargo/bin")


def _tool_env() -> dict:
    """PATH for a GUI app, which starts with only /usr/bin:/bin and cannot find brew, uv, npm."""
    extra = [os.path.expanduser(p) for p in TOOL_PATHS]
    return {**os.environ, "PATH": ":".join(extra + [os.environ.get("PATH", "")])}


def system_cache_locations(home: Path | None = None) -> list[dict]:
    """Well-known tool caches outside lab/active that regenerate on demand.

    Each entry: label, path, kb, argv (the tool's own cleanup, or None), default (ticked
    when the dialog opens), auto (False = reported only, never run from the app) and
    note. Without the tool installed, an entry with auto=True falls back to emptying
    its folder.
    """
    home = home or Path.home()
    lib = home / "Library"
    spec = [
        # label, path, argv, default ticked, auto, note
        ("pip", lib / "Caches" / "pip", ["pip", "cache", "purge"], True, True, ""),
        ("uv", home / ".cache" / "uv", ["uv", "cache", "clean"], True, True, ""),
        ("uv (Library)", lib / "Caches" / "uv", ["uv", "cache", "clean"], True, True, ""),
        ("Homebrew downloads", lib / "Caches" / "Homebrew",
         ["brew", "cleanup", "--prune=all"], True, True, ""),
        ("npm", home / ".npm" / "_cacache", ["npm", "cache", "clean", "--force"], True, True, ""),
        ("pnpm store", lib / "pnpm", ["pnpm", "store", "prune"], True, True, ""),
        ("Yarn", lib / "Caches" / "Yarn", ["yarn", "cache", "clean"], True, True, ""),
        ("Xcode DerivedData", lib / "Developer" / "Xcode" / "DerivedData", None, True, True,
         "build output; Xcode recreates it on the next build"),
        ("Unavailable simulators", lib / "Developer" / "CoreSimulator",
         ["xcrun", "simctl", "delete", "unavailable"], False, True,
         "removes only simulators of old Xcode versions; the size shown is all simulators"),
        ("Hugging Face models", home / ".cache" / "huggingface", None, False, True,
         "downloaded models; each re-downloads (can be GBs) when a project loads it again"),
        ("PyTorch models", home / ".cache" / "torch", None, False, True,
         "downloaded weights; they re-download when used again"),
        ("Docker data", lib / "Containers" / "com.docker.docker", None, False, False,
         "images and volumes may hold data: clean in Docker Desktop or `docker system prune`"),
    ]
    out = []
    seen = set()
    for label, path, argv, default, auto, note in spec:
        if path.exists() and path not in seen:
            seen.add(path)
            out.append({"label": label, "path": path, "kb": _du_kb(path), "argv": argv,
                        "default": default, "auto": auto, "note": note,
                        "cmd": " ".join(argv) if argv else "empty the folder"})
    out.sort(key=lambda d: -d["kb"])
    return out


def clean_system_cache(item: dict, home: Path | None = None) -> tuple[bool, str]:
    """Run the cache's own cleanup, or empty its folder when the tool is missing or
    there is none. Refuses anything not auto, outside the home folder, or a symlink."""
    home = (home or Path.home()).resolve()
    if not item.get("auto"):
        return False, "not cleaned from here"
    path = Path(item["path"])
    try:
        inside = path.resolve().relative_to(home) is not None
    except ValueError:
        inside = False
    if not inside or path.is_symlink():
        return False, "refused: not a plain folder inside your home folder"
    argv = item.get("argv")
    env = _tool_env()
    if argv and shutil.which(argv[0], path=env["PATH"]):
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=900, env=env)
        except (OSError, subprocess.SubprocessError) as e:
            return False, f"{argv[0]}: {e}"
        if r.returncode == 0:
            return True, "cleaned with " + " ".join(argv)
        lines = (r.stdout + r.stderr).strip().splitlines()
        return False, lines[-1] if lines else f"{argv[0]} failed"
    if argv and not path.is_dir():
        return False, f"{argv[0]} not installed"
    failed = 0
    for child in path.iterdir():
        try:
            if child.is_symlink() or child.is_file():
                child.unlink()
            else:
                shutil.rmtree(child)
        except OSError:
            failed += 1
    return failed == 0, ("emptied the folder" if not failed else f"{failed} items could not be removed")
