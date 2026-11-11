#!/usr/bin/env python3
"""Legal sign-off gate: agents prepare and check, a person signs, and Release waits for it.

    python3 docs/foundry/tooling/legal_gate.py status <app>
    python3 docs/foundry/tooling/legal_gate.py check  <app>     exit 0 = Release may start
    python3 docs/foundry/tooling/legal_gate.py sign   <app> --by NAME --role owner|lawyer
                                                      [--scope TEXT] [--accept-risk WHY]

The tier comes from `tier:` under `## Distribution` in docs/foundry/app-context.md. A sign-off is
one line in docs/legal/signoff.jsonl, bound to a hash of every other file under docs/legal/, so
any later edit to the pack makes it stale. `sign` needs an interactive terminal and a typed
confirmation: it is run by the owner or a lawyer, never by an agent.
Stdlib only. Reads the app; `sign` writes only docs/legal/signoff.jsonl.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TIERS = ("internal", "public", "commercial", "client")
NEEDS_SIGNOFF = ("public", "commercial", "client")
ROLES = ("owner", "lawyer")
SIGNOFF = "signoff.jsonl"
REGISTER = "register.md"
# What a pack must hold before it can be signed, per tier (docs/legal/<name>). `terms.md` and
# `ai-act.md` are also expected for `public` when the product needs disclaimers or uses a model;
# that is the agent's and the signer's judgement, so it is not enforced here.
REQUIRED = {"public": ("register.md", "licences.md", "privacy.md", "name.md"),
            "commercial": ("register.md", "licences.md", "privacy.md", "name.md", "terms.md"),
            "client": ("register.md", "licences.md", "privacy.md", "name.md", "terms.md")}
TRIGGER = re.compile(r"^\s*[-*] \[ \]\s*\**LAWYER\b\**:?\s*(.*)$", re.M)


def foundry_dir(app: Path) -> Path:
    """The app's Foundry folder, docs/foundry. An app not yet updated to Foundry v7 still has
    docs/company; it is read until `install.sh --update` has moved it."""
    new, old = app / "docs" / "foundry", app / "docs" / "company"
    return old if old.is_dir() and not new.is_dir() else new


PROPOSED = "not yet confirmed by the owner"


def _distribution(app: Path) -> str:
    """The text of the `## Distribution` section of app-context ('' when there is none)."""
    try:
        text = (foundry_dir(app) / "app-context.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = re.search(r"^##\s*Distribution\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def tier(app: Path) -> str | None:
    """The tier named under `## Distribution` in app-context; None when unset or not a known tier."""
    t = re.search(r"^\s*tier:\s*`?([a-z-]+)`?", _distribution(app), re.M)
    return t.group(1) if t and t.group(1) in TIERS else None


def tier_proposed(app: Path) -> bool:
    """An agent may propose a tier but not set it: while the section still says
    'not yet confirmed by the owner', the tier is shown and Release stays stopped. The owner
    confirms by deleting that line."""
    return PROPOSED in _distribution(app).lower()


def pack_files(app: Path) -> list[Path]:
    legal = app / "docs" / "legal"
    if not legal.is_dir():
        return []
    return sorted(p for p in legal.rglob("*")
                  if p.is_file() and p.name != SIGNOFF and not p.name.startswith("."))


def pack_hash(app: Path) -> str | None:
    """sha256 over the relative path and bytes of every pack file; None when the pack is empty."""
    files = pack_files(app)
    if not files:
        return None
    h = hashlib.sha256()
    for p in files:
        h.update(p.relative_to(app).as_posix().encode("utf-8") + b"\0")
        h.update(p.read_bytes() + b"\0")
    return h.hexdigest()


def open_triggers(app: Path) -> list[str]:
    """Open `- [ ] LAWYER: ...` lines in the register: things only a qualified person may clear."""
    try:
        text = (app / "docs" / "legal" / REGISTER).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [m.group(1).strip() for m in TRIGGER.finditer(text)]


def missing_files(app: Path, t: str | None) -> list[str]:
    """Pack files the tier requires that are absent or empty."""
    legal = app / "docs" / "legal"
    return [n for n in REQUIRED.get(t or "", ())
            if not (legal / n).is_file() or not (legal / n).read_text(encoding="utf-8", errors="replace").strip()]


def signoffs(app: Path) -> list[dict]:
    out = []
    try:
        lines = (app / "docs" / "legal" / SIGNOFF).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and e.get("hash") and e.get("by") and e.get("role") in ROLES:
            out.append(e)
    return out


def evaluate(app: Path) -> dict:
    """Everything `status`, `check` and the dashboard need. `ok` is the gate's verdict."""
    t, h, trig, signs = tier(app), pack_hash(app), open_triggers(app), signoffs(app)
    last = signs[-1] if signs else None
    current = [s for s in signs if s["hash"] == h] if h else []
    reasons: list[str] = []
    proposed = t is not None and tier_proposed(app)
    if t is None:
        reasons.append("no distribution tier in docs/foundry/app-context.md (## Distribution, tier:)")
    elif proposed:
        reasons.append(f"distribution tier {t} is proposed, {PROPOSED}: to confirm, delete that "
                       "line under ## Distribution in docs/foundry/app-context.md")
    elif t in NEEDS_SIGNOFF:
        gaps = missing_files(app, t)
        if not (app / "docs" / "legal" / REGISTER).is_file():
            reasons.append("no legal pack: docs/legal/register.md is missing")
        elif gaps:
            reasons.append(f"legal pack incomplete for tier {t}: missing {', '.join(gaps)}")
        elif not signs:
            reasons.append("no legal sign-off recorded")
        elif not current:
            reasons.append(f"legal pack changed since the last sign-off ({last['by']}, {last['ts'][:10]})")
        elif trig and not any(s["role"] == "lawyer" or s.get("risk_accepted") for s in current):
            reasons.append(f"{len(trig)} open lawyer trigger(s): needs a lawyer's sign-off, "
                           "or the owner's with --accept-risk")
    return {"tier": t, "tier_proposed": proposed, "needs_signoff": t in NEEDS_SIGNOFF, "hash": h,
            "files": [p.relative_to(app).as_posix() for p in pack_files(app)],
            "open_triggers": trig, "last_signoff": last,
            "valid_signoff": current[-1] if current else None, "ok": not reasons, "reasons": reasons}


def _commit(app: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(app), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def sign(app: Path, by: str, role: str, scope: str = "", accept_risk: str = "",
         interactive: bool = False, confirm=input, now: datetime | None = None) -> dict:
    """Append a sign-off for the pack as it is now. Raises PermissionError unless a person is at
    a terminal and types the app's folder name; ValueError when there is nothing valid to sign."""
    if not interactive:
        raise PermissionError("a sign-off is recorded by a person in a terminal, never by an agent or a script")
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    if not by.strip():
        raise ValueError("--by needs the signer's name")
    state = evaluate(app)
    if state["tier"] is None:
        raise ValueError("set the distribution tier in app-context first")
    if state["hash"] is None or not (app / "docs" / "legal" / REGISTER).is_file():
        raise ValueError("nothing to sign: docs/legal/register.md is missing")
    gaps = missing_files(app, state["tier"])
    if gaps:
        raise ValueError(f"pack incomplete for tier {state['tier']}: missing {', '.join(gaps)}")
    trig = state["open_triggers"]
    if trig and role != "lawyer" and not accept_risk.strip():
        raise ValueError(f"{len(trig)} open lawyer trigger(s): sign as --role lawyer, or accept the risk "
                         'in writing with --accept-risk "<why>"')
    name = app.resolve().name
    typed = confirm(f"You are signing off {len(state['files'])} file(s) under docs/legal/ of '{name}' "
                    f"as {role} ({by}).\nOpen lawyer triggers: {len(trig)}. "
                    f"Type the app name to confirm: ")
    if typed.strip() != name:
        raise PermissionError("confirmation did not match; nothing recorded")
    entry = {"ts": (now or datetime.now()).isoformat(timespec="seconds"), "by": by.strip(), "role": role,
             "tier": state["tier"], "hash": state["hash"], "files": len(state["files"]),
             "commit": _commit(app), "scope": scope.strip() or "whole pack",
             "open_triggers": trig, "risk_accepted": accept_risk.strip() or None}
    with (app / "docs" / "legal" / SIGNOFF).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("status", "check"):
        sub.add_parser(name).add_argument("app", type=Path)
    sp = sub.add_parser("sign")
    sp.add_argument("app", type=Path)
    sp.add_argument("--by", required=True)
    sp.add_argument("--role", required=True, choices=ROLES)
    sp.add_argument("--scope", default="")
    sp.add_argument("--accept-risk", default="")
    a = ap.parse_args(argv)
    if not (a.app / "docs").is_dir():
        print(f"not an app with a docs/ folder: {a.app}", file=sys.stderr)
        return 2
    if a.cmd == "sign":
        try:
            e = sign(a.app, a.by, a.role, a.scope, a.accept_risk,
                     interactive=sys.stdin.isatty() and sys.stdout.isatty())
        except (PermissionError, ValueError, EOFError, KeyboardInterrupt) as err:
            print(f"not signed: {err}", file=sys.stderr)
            return 1
        print(f"signed: {e['by']} ({e['role']}) {e['ts']} pack {e['hash'][:12]}")
        return 0
    s = evaluate(a.app)
    if a.cmd == "status":
        last = s["last_signoff"]
        print(f"tier: {s['tier'] or 'unclassified'}")
        print(f"pack: {len(s['files'])} file(s), hash {s['hash'][:12] if s['hash'] else 'none'}")
        print("last sign-off: " + (f"{last['by']} ({last['role']}) {last['ts']} pack {last['hash'][:12]}"
                                   + (" [current]" if last["hash"] == s["hash"] else " [STALE: pack changed]")
                                   if last else "none"))
        for t in s["open_triggers"]:
            print(f"open lawyer trigger: {t}")
    if s["ok"]:
        print("legal gate: clear" + ("" if s["needs_signoff"] else " (tier internal needs no sign-off)"))
        return 0
    for r in s["reasons"]:
        print(f"legal gate: BLOCKED: {r}")
    return 1 if a.cmd == "check" else 0


if __name__ == "__main__":
    sys.exit(main())
