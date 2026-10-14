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
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith(".noindex")]
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
