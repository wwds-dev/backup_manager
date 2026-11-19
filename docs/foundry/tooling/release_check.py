#!/usr/bin/env python3
"""Release check: the first step of every release, run by the app's release script and CI.

    python3 docs/foundry/tooling/release_check.py .                   exit 0 = Release may start
    python3 docs/foundry/tooling/release_check.py . --hq <foundry>    tier client: also the order gate
    python3 docs/foundry/tooling/release_check.py . --ci              in CI: legal gate only (see below)

1. The legal gate (`legal_gate.py check`): tier set and confirmed, the pack the tier needs, a
   current sign-off where the tier needs one. Its warnings are printed and do not block.
2. Tier `client`: `order.py gate <id> done` in the Foundry HQ (`order: <id>` under
   `## Distribution` in app-context). The order is private and lives only in the HQ, so this needs
   the HQ on this machine: `--hq PATH` or `FOUNDRY_HQ`. Without it the check fails. `--ci` says
   "no HQ here": the legal gate still runs and the order gate is reported NOT CHECKED, so a green
   CI release job for a client app does not mean the delivery was accepted; the orchestrator runs
   the order gate in the HQ (AGENTS.md, "Client delivery").

A pack kept in the HQ (`install.sh --legal-in-hq`) is a git-ignored link that a CI clone does not
have, so for such an app this check can pass only on the owner's machine: say so, never skip it.
Stdlib only. Reads the app and, for `client`, runs the HQ's order.py; writes nothing.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _legal_gate():
    spec = importlib.util.spec_from_file_location("legal_gate", HERE / "legal_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def order_id(lg, app: Path) -> str | None:
    """The `order: <id>` line under ## Distribution (tier client)."""
    m = re.search(r"^\s*order:\s*`?([A-Za-z0-9._-]+)`?", lg._distribution(app), re.M)
    return m.group(1) if m else None


def _pack_in_hq_missing(app: Path) -> bool:
    """docs/legal is listed in the app's .gitignore (pack kept in the HQ) but absent here."""
    try:
        ignored = (app / ".gitignore").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return (not (app / "docs" / "legal").exists()
            and bool(re.search(r"^/?docs/legal/?\s*$", ignored, re.M)))


def check(app: Path, hq: Path | None = None, ci: bool = False, run=subprocess.run) -> tuple[bool, list[str]]:
    """(ok, lines to print). Fails closed: anything it cannot check is a BLOCKED line."""
    lg = _legal_gate()
    s = lg.evaluate(app)
    out = [f"release check: WARNING: {w}" for w in s.get("warnings", [])]
    ok = s["ok"]
    for r in s["reasons"]:
        out.append(f"release check: BLOCKED: legal gate: {r}")
    if not s["ok"] and _pack_in_hq_missing(app):
        out.append("release check: BLOCKED: the legal pack is kept in the Foundry HQ (docs/legal is a "
                   "git-ignored link) and is not here: run this check on the owner's machine")
    if s["ok"]:
        out.append(f"release check: legal gate clear (tier {s['tier']})")
    if s["tier"] == "client":
        oid = order_id(lg, app)
        if oid is None:
            ok = False
            out.append("release check: BLOCKED: tier client needs `order: <id>` under ## Distribution")
        elif ci:
            out.append(f"release check: order gate NOT CHECKED in CI (order {oid} lives only in the "
                       f"Foundry HQ): the orchestrator runs `python3 tools/order.py gate {oid} done` there")
        elif hq is None:
            ok = False
            out.append("release check: BLOCKED: tier client: the order gate needs the Foundry HQ "
                       "(--hq PATH or FOUNDRY_HQ); --ci checks the legal gate only")
        elif not (hq / "tools" / "order.py").is_file():
            ok = False
            out.append(f"release check: BLOCKED: no tools/order.py in {hq}")
        else:
            try:
                r = run([sys.executable, str(hq / "tools" / "order.py"), "gate", oid, "done"],
                        capture_output=True, text=True, timeout=60)
                code, text = r.returncode, (r.stdout + r.stderr).strip()
            except (OSError, subprocess.SubprocessError) as err:
                code, text = 2, f"order gate did not run: {err}"
            out += [f"release check: {line}" for line in text.splitlines()]
            if code != 0:
                ok = False
                out.append(f"release check: BLOCKED: order gate {oid} done exited {code}")
    out.append("release check: " + ("clear: Release may start" if ok else "BLOCKED: do not build or publish"))
    return ok, out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("app", type=Path)
    ap.add_argument("--hq", type=Path, default=None, help="Foundry HQ checkout (default: $FOUNDRY_HQ)")
    ap.add_argument("--ci", action="store_true", help="no HQ here: check the legal gate only")
    a = ap.parse_args(argv)
    if not (a.app / "docs").is_dir():
        print(f"not an app with a docs/ folder: {a.app}", file=sys.stderr)
        return 2
    hq = a.hq or (Path(os.environ["FOUNDRY_HQ"]) if os.environ.get("FOUNDRY_HQ") else None)
    ok, lines = check(a.app, hq=hq, ci=a.ci)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
