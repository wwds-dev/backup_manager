#!/usr/bin/env python3
"""Append one pipeline event to an app's docs/company/activity.jsonl (read by company_status.py).

    python3 docs/company/tooling/log_activity.py . <phase> <start|done|blocked> [--spec SLUG] [--note TEXT]

phase: define design architect build review verify secure document release
The Foundry dashboard shows a phase as active while its latest event is `start` and under 12 hours old.
It only feeds the dashboard: a failure to log must never block the work.
Stdlib only. Writes only that one file.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PHASES = ["define", "design", "architect", "build", "review", "verify", "secure", "document", "release"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("app", type=Path)
    ap.add_argument("phase", choices=PHASES)
    ap.add_argument("state", choices=["start", "done", "blocked"])
    ap.add_argument("--spec", default=None)
    ap.add_argument("--note", default=None)
    a = ap.parse_args(argv)
    if not (a.app / "docs").is_dir():
        print(f"not an app with a docs/ folder: {a.app}", file=sys.stderr)
        return 2
    log = a.app / "docs" / "company" / "activity.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": datetime.now().isoformat(timespec="seconds"), "phase": a.phase, "state": a.state}
    if a.spec:
        event["spec"] = a.spec
    if a.note:
        event["note"] = a.note
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(f"logged {a.phase} {a.state} -> {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
