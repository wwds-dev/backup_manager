#!/usr/bin/env python3
"""Claude Code SessionStart hook: say in one line whether this checkout is a Foundry app.

Registered by install.sh in the app's .claude/settings.json (and, optionally, once in the owner's
~/.claude/settings.json so a hand-made app is caught too). Whatever this prints is added to the
session's context, so it prints one line when all is well and a warning only when something is
missing. Standard library only, Python 3.9+, never fails a session: any error exits 0 silently.

    python3 docs/foundry/tooling/session_start.py            # as a hook (JSON on stdin)
    python3 docs/foundry/tooling/session_start.py --cwd DIR  # by hand
"""
import json
import os
import re
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
    return line


def main() -> int:
    try:
        data = {}
        if "--cwd" in sys.argv:
            cwd = sys.argv[sys.argv.index("--cwd") + 1]
        else:
            if not sys.stdin.isatty():
                raw = sys.stdin.read()
                data = json.loads(raw) if raw.strip() else {}
            cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        if data.get("source") == "resume":
            return 0                                # the line is already in the resumed context
        sid = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("session_id", "")))
        if sid:                                     # registered twice (app and user settings): print once
            stamp = Path(tempfile.gettempdir()) / ("foundry-session-%s-%s" % (sid, data.get("source", "")))
            try:
                if stamp.exists() and time.time() - stamp.stat().st_mtime < 30:
                    return 0
                stamp.write_text("", encoding="utf-8")
            except OSError:
                pass
        root = app_root(Path(cwd).expanduser().resolve())
        out = report(root) if root else ""
        if out:
            print(out)
    except Exception:                               # a hook must never break a session
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
