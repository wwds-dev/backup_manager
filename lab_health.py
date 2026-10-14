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


def cleanup_targets(rows: list[dict], checked: set[int]) -> list[tuple[str, Path, int]]:
    """(project, path, kb) to delete for the checked rows. External projects are
    skipped and every path must sit inside its project, whatever the UI shows."""
    targets = []
    for i in sorted(checked):
        if i >= len(rows) or rows[i].get("external"):
            continue
        row = rows[i]
        base = Path(row["path"]).resolve()
        for p, kb in row["reclaim_items"]:
            p = Path(p)
            if p.is_symlink():
                continue
            try:
                p.resolve().relative_to(base)
            except ValueError:
                continue
            if p.resolve() != base:
                targets.append((row["name"], p, kb))
    return targets


def commit_target(rows: list[dict], selected: list[int]) -> dict | None:
    """The row the Commit button acts on: exactly one selected row with changes."""
    if len(selected) != 1 or not 0 <= selected[0] < len(rows):
        return None
    row = rows[selected[0]]
    return row if row.get("has_git") and row.get("uncommitted") else None
