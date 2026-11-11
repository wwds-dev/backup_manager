#!/usr/bin/env python3
"""Write the app's plan: docs/foundry/plan.toml (read by the Foundry workspace's Roadmap and Time & money).

    python3 docs/foundry/tooling/plan.py . set [--estimate-hours H] [--budget-usd N] [--eval-budget-usd N]
                                               [--rate-eur N] [--due YYYY-MM-DD] [--horizon now|next|later]
    python3 docs/foundry/tooling/plan.py . milestone "<name>" --due YYYY-MM-DD [--start D] [--spec SLUG]
    python3 docs/foundry/tooling/plan.py . done "<name>" [--on YYYY-MM-DD]
    python3 docs/foundry/tooling/plan.py . show

Writers: /ship-feature's Plan phase (a milestone per spec, the estimate for the change) and the
business case (budget, rate). The numbers are estimates someone made, never measurements: the
workspace compares them with the measured agent time and model use. A field left out stays
"not recorded"; nothing here fills in a default. Stdlib only (Python 3.11+ for tomllib).
Writes only that one file.

Format:
    estimate_hours = 30.0        # owner and agent hours for the planned work
    model_budget_usd = 90.0      # model and API budget
    eval_budget_usd = 5.0        # optional: the part of it for live evals of the app's own model calls
                                 # (qa-engineer playbook); runs are counted in model_use.jsonl
    hourly_rate_eur = 60.0       # optional: the owner's rate, for a margin on client work
    due = "2026-12-05"
    horizon = "now"              # now | next | later
    updated = "2026-11-11"       # set by this tool
    [[milestone]]
    name = "v2 public source release"
    due = "2026-11-21"
    start = "2026-11-12"         # optional
    spec = "legal-fixes"         # optional: the spec this milestone delivers
    done = "2026-11-20"          # set by `done`
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None

TOP = ("estimate_hours", "model_budget_usd", "eval_budget_usd", "hourly_rate_eur", "due", "horizon", "updated")
MS = ("name", "due", "start", "spec", "done")


def _date(s: str) -> str:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s or ""):
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD): {s}")
    date.fromisoformat(s)
    return s


def _pos(s: str) -> float:
    v = float(s)
    if v <= 0:
        raise argparse.ArgumentTypeError("must be above 0 (leave it out when it is not known)")
    return v


def _val(v) -> str:
    return json.dumps(v, ensure_ascii=False) if isinstance(v, str) else repr(float(v)) if isinstance(v, float) else str(v)


def dump(plan: dict) -> str:
    """The plan as TOML: top-level keys, then one [[milestone]] table each (strings JSON-quoted,
    which is valid TOML for basic strings)."""
    lines = ["# Foundry plan: estimates and milestones. Written by docs/foundry/tooling/plan.py.",
             "# Read by the Foundry workspace. A missing key is shown as 'not recorded'."]
    lines += [f"{k} = {_val(plan[k])}" for k in TOP if plan.get(k) is not None]
    for m in plan.get("milestone", []):
        lines += ["", "[[milestone]]"] + [f"{k} = {_val(m[k])}" for k in MS if m.get(k) is not None]
    return "\n".join(lines) + "\n"


def load(path: Path) -> dict:
    if not path.is_file():
        return {}
    if tomllib is None:
        sys.exit("plan.py needs Python 3.11+ (tomllib)")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("app", type=Path)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("--estimate-hours", type=_pos)
    s.add_argument("--budget-usd", type=_pos)
    s.add_argument("--eval-budget-usd", type=_pos)
    s.add_argument("--rate-eur", type=_pos)
    s.add_argument("--due", type=_date)
    s.add_argument("--horizon", choices=["now", "next", "later"])
    m = sub.add_parser("milestone")
    m.add_argument("name")
    m.add_argument("--due", type=_date, required=True)
    m.add_argument("--start", type=_date)
    m.add_argument("--spec")
    d = sub.add_parser("done")
    d.add_argument("name")
    d.add_argument("--on", type=_date, default=date.today().isoformat())
    sub.add_parser("show")
    a = ap.parse_args(argv)
    if not (a.app / "docs").is_dir():
        print(f"not an app with a docs/ folder: {a.app}", file=sys.stderr)
        return 2
    path = a.app / "docs" / "foundry" / "plan.toml"
    plan = load(path)
    if a.cmd == "show":
        print(path.read_text(encoding="utf-8") if path.is_file() else f"no plan yet: {path}")
        return 0
    ms = [dict(x) for x in plan.get("milestone", [])]
    if a.cmd == "set":
        vals = {"estimate_hours": a.estimate_hours, "model_budget_usd": a.budget_usd,
                "eval_budget_usd": a.eval_budget_usd,
                "hourly_rate_eur": a.rate_eur, "due": a.due, "horizon": a.horizon}
        if all(v is None for v in vals.values()):
            print("nothing to set", file=sys.stderr)
            return 2
        plan.update({k: v for k, v in vals.items() if v is not None})
    elif a.cmd == "milestone":
        hit = next((x for x in ms if x.get("name") == a.name), None)
        new = {"name": a.name, "due": a.due, "start": a.start, "spec": a.spec}
        if hit:
            hit.update({k: v for k, v in new.items() if v is not None})
        else:
            ms.append({k: v for k, v in new.items() if v is not None})
    elif a.cmd == "done":
        hit = next((x for x in ms if x.get("name") == a.name), None)
        if not hit:
            print(f"no milestone named {a.name!r}", file=sys.stderr)
            return 2
        hit["done"] = a.on
    plan["milestone"] = ms
    plan["updated"] = date.today().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(plan), encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
