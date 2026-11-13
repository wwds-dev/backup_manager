#!/usr/bin/env python3
"""Claude Code SessionStart hook: say in one line whether this checkout is a Foundry app.

Registered by install.sh in the app's .claude/settings.json (and, optionally, once in the owner's
~/.claude/settings.json so a hand-made app is caught too). Whatever this prints is added to the
session's context, so it prints one line when all is well and a warning only when something is
missing. Standard library only, Python 3.9+, never fails a session: any error exits 0 silently.

    python3 docs/foundry/tooling/session_start.py            # as a hook (JSON on stdin)
    python3 docs/foundry/tooling/session_start.py --cwd DIR  # by hand
    python3 docs/foundry/tooling/session_start.py --inflight # work another session may own
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AGENTS_MAX_LINES = 150
EXEMPT = ".foundry-exempt"   # a file with one line saying why this repo is not a Foundry app


def app_root(start: Path):
    """The nearest folder, from start upward, that is a Foundry app or a git checkout."""
    for d in [start, *start.parents]:
        if (d / "docs" / "foundry" / "app-context.md").is_file() or (d / ".git").exists():
            return d
    return None


def _git(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def inflight(root: Path) -> list:
    """Work another session may own: unreleased specs, unmerged claude/* branches, other worktrees."""
    out = []
    latest = {}                                     # spec -> (phase, state, ts) of its newest event
    try:
        for ln in (root / "docs" / "foundry" / "activity.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("spec"):
                latest[r["spec"]] = (r.get("phase", "?"), r.get("state", r.get("event", "")), str(r.get("ts", r.get("at", "")))[:10])
    except OSError:
        pass
    specs = [("%s (%s %s %s)" % (s, p, st, ts)).replace("  ", " ") for s, (p, st, ts) in sorted(latest.items())
             if not (p == "release" and st == "done")]
    if specs:
        out.append("specs not released: " + ", ".join(specs))
    base = ""
    for cand in ("main", "master"):
        if _git(root, "rev-parse", "--verify", "-q", cand).strip():
            base = cand
            break
    if base:
        names = [b.strip().lstrip("*+ ") for b in _git(root, "branch", "--list", "claude/*", "--no-merged", base).splitlines() if b.strip()]
        ahead = []
        for b in names:
            n = _git(root, "rev-list", "--count", "%s..%s" % (base, b)).strip()
            ahead.append("%s (+%s)" % (b, n or "?"))
        if ahead:
            out.append("unmerged branches: " + ", ".join(ahead))
    wts = [ln[9:] for ln in _git(root, "worktree", "list", "--porcelain").splitlines() if ln.startswith("worktree ")]
    others = [w for w in wts if Path(w).resolve() != root.resolve()]
    if others:
        out.append("other worktrees: " + ", ".join(others))
    return out


def inflight_line(root: Path) -> str:
    items = inflight(root)
    if not items:
        return ""
    return ("IN FLIGHT: " + "; ".join(items) + ". Before starting a change, check it is not one of these; "
            "if it is, stop and tell the owner. A session started by another session starts no further sessions.")


def report(root: Path) -> str:
    if (root / "template" / "AGENTS.md").is_file() and (root / "apps.md").is_file():
        return ""                                   # the Foundry HQ itself
    ctx_file = root / "docs" / "foundry" / "app-context.md"
    if not ctx_file.is_file():
        if (root / EXEMPT).is_file() or root.parent.name != "active":
            return ""                               # exempt, or not a lab project at all
        return ("NOT A FOUNDRY APP: %s has no docs/foundry/app-context.md. Before any feature work, tell "
                "the owner and adopt it with /adopt-app in the Foundry HQ (or add a %s file saying why "
                "not). Do not build outside the pipeline." % (root.name, EXEMPT))
    ctx = ctx_file.read_text(encoding="utf-8", errors="replace")
    warn = []
    m = re.search(r"^tier:\s*([a-z]+)", ctx, re.M)
    tier = m.group(1) if m else None
    if not tier:
        warn.append("no distribution tier (Release is stopped)")
    elif "proposed by agent, not yet confirmed by the owner" in ctx:
        warn.append("tier %s is only proposed (Release is stopped until the owner confirms)" % tier)
    holes = len(re.findall(r"^<[^>\n]*(?:>|$)", ctx, re.M))
    if holes:
        warn.append("%d unfilled placeholder(s) in app-context.md" % holes)
    agents = root / "AGENTS.md"
    if not agents.is_file():
        warn.append("AGENTS.md is missing")
    else:
        n = len(agents.read_text(encoding="utf-8", errors="replace").splitlines())
        if n > AGENTS_MAX_LINES:
            warn.append("AGENTS.md is %d lines (limit %d): move detail into docs/" % (n, AGENTS_MAX_LINES))
    if not (root / "CLAUDE.md").is_file():
        warn.append("CLAUDE.md is missing, so Claude Code does not load AGENTS.md (it should hold @AGENTS.md)")
    if not (root / "docs" / "foundry" / "PROCESS.md").is_file():
        warn.append("docs/foundry/PROCESS.md is missing: run Foundry's install.sh --update")
    last = ""
    try:
        rows = (root / "docs" / "foundry" / "activity.jsonl").read_text(encoding="utf-8").strip().splitlines()
        if rows:
            r = json.loads(rows[-1])
            last = " Last logged: %s %s%s." % (r.get("phase", "?"), r.get("event", r.get("state", "")),
                                               (" (" + str(r.get("at", r.get("ts", "")))[:10] + ")") if (r.get("at") or r.get("ts")) else "")
    except (OSError, ValueError, AttributeError):
        pass
    line = ("Foundry app: %s, tier %s.%s Read docs/foundry/app-context.md, then state which pipeline phase "
            "this session's work belongs to." % (root.name, tier or "UNSET", last))
    if warn:
        line += "\nFOUNDRY WARNINGS: " + "; ".join(warn) + ". Tell the owner before building."
    flight = inflight_line(root)
    return line + ("\n" + flight if flight else "")


def main() -> int:
    try:
        data = {}
        if "--cwd" in sys.argv:
            cwd = sys.argv[sys.argv.index("--cwd") + 1]
        else:
            if "--inflight" not in sys.argv and not sys.stdin.isatty():
                raw = sys.stdin.read()
                data = json.loads(raw) if raw.strip() else {}
            cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        if "--inflight" not in sys.argv and data.get("source") == "resume":
            return 0                                # the line is already in the resumed context
        sid = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id", "")))
        if sid and "--inflight" not in sys.argv:                                     # registered twice (app and user settings): print once
            stamp = Path(tempfile.gettempdir()) / ("foundry-session-%s-%s" % (sid, data.get("source", "")))
            try:
                if stamp.exists() and time.time() - stamp.stat().st_mtime < 30:
                    return 0
                stamp.write_text("", encoding="utf-8")
            except OSError:
                pass
        root = app_root(Path(cwd).expanduser().resolve())
        if "--inflight" in sys.argv:
            items = inflight(root) if root else []
            print("\n".join(items) if items else "nothing in flight")
            return 0
        out = report(root) if root else ""
        if out:
            print(out)
    except Exception:                               # a hook must never break a session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
