#!/usr/bin/env python3
"""Fail if a quality count rose above its recorded baseline.

    ratchet.py NAME COUNT_COMMAND...      compare; exit 1 if count > baseline
    ratchet.py --update NAME COUNT_COMMAND...   record a lower (or first) baseline

COUNT_COMMAND prints findings one per line (or a single integer); the count is the number of
non-empty lines, or the integer. The baseline lives in baseline.json next to this script.
"""
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).with_name("baseline.json")


def count(cmd: list[str]) -> int:
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    if out.isdigit():
        return int(out)
    return sum(1 for line in out.splitlines() if line.strip())


def main(argv: list[str]) -> int:
    update = argv[:1] == ["--update"]
    argv = argv[1:] if update else argv
    if len(argv) < 2:
        print(__doc__)
        return 2
    name, cmd = argv[0], argv[1:]
    data = json.loads(BASE.read_text()) if BASE.is_file() else {}
    now = count(cmd)
    if update:
        if name in data and now > data[name]:
            print(f"{name}: {now} is above baseline {data[name]}; refusing to raise it")
            return 1
        data[name] = now
        BASE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        print(f"{name}: baseline set to {now}")
        return 0
    if name not in data:
        print(f"{name}: no baseline recorded (run with --update)")
        return 1
    if now > data[name]:
        print(f"{name}: {now} findings, baseline {data[name]}: the count rose")
        return 1
    print(f"{name}: {now} findings, baseline {data[name]}: ok" + (" (improved: run --update)" if now < data[name] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
