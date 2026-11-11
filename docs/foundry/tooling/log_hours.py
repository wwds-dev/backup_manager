#!/usr/bin/env python3
"""Record hours the owner spent on this app in docs/foundry/time.jsonl (read by the Foundry workspace).

    python3 docs/foundry/tooling/log_hours.py . <hours> [--on YYYY-MM-DD] [--note TEXT]

The owner's own time is not in any log a machine keeps, so it is a manual entry: the owner runs
this, or tells an agent the number to enter. Agent time and model use are measured separately
from Claude Code's transcripts (dashboard/foundry_usage.py in the HQ) and never written here.
One JSON object per line: {ts, date, hours, who: "owner", note?}. Stdlib only. Writes only that file.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("app", type=Path)
    ap.add_argument("hours", type=float)
    ap.add_argument("--on", default=date.today().isoformat())
    ap.add_argument("--note", default=None)
    a = ap.parse_args(argv)
    try:
        day = date.fromisoformat(a.on)
    except ValueError:
        print(f"not a date (YYYY-MM-DD): {a.on}", file=sys.stderr)
        return 2
    if not 0 < a.hours <= 24:
        print("hours must be above 0 and at most 24 for one day", file=sys.stderr)
        return 2
    if day > date.today():
        print("a day in the future cannot have hours yet", file=sys.stderr)
        return 2
    if not (a.app / "docs").is_dir():
        print(f"not an app with a docs/ folder: {a.app}", file=sys.stderr)
        return 2
    log = a.app / "docs" / "foundry" / "time.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    e = {"ts": datetime.now().isoformat(timespec="seconds"), "date": day.isoformat(), "hours": round(a.hours, 2),
         "who": "owner"}
    if a.note:
        e["note"] = a.note
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"logged {e['hours']} h on {e['date']} -> {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
