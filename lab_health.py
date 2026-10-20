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


def classify_item(proj: Path, folder: Path, kb: int, idle: int | None) -> dict:
    """One reclaimable folder with what it costs to delete and whether it is offered.
    kind 'junk' regenerates by itself; kind 'env' needs a rebuild, so it is offered
    only when it can be rebuilt AND the project has been idle for IDLE_DAYS."""
    item = {"path": folder, "kb": kb, "kind": "junk", "rebuild": None,
            "eligible": True, "reason": ""}
    if folder.name in JUNK_NAMES:
        return item
    item["kind"] = "env"
    item["rebuild"] = rebuild_command(proj, folder)
    if item["rebuild"] is None:
        item["eligible"] = False
        item["reason"] = "no lockfile or manifest, so it could not be rebuilt"
    elif idle is None or idle < IDLE_DAYS:
        item["eligible"] = False
        item["reason"] = ("activity unknown" if idle is None
                          else f"project active {idle} day{'s' if idle != 1 else ''} ago "
                               f"(offered after {IDLE_DAYS})")
    return item


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
