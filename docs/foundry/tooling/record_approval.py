#!/usr/bin/env python3
"""Record the owner's approval of an ordinary pipeline gate in docs/foundry/approvals.jsonl.

    python3 docs/foundry/tooling/record_approval.py . <gate> --words "<the owner's words, verbatim>"
                                                     [--spec SLUG] [--note TEXT]

gate: case define design architect plan release, or `decision` for an owner decision outside a gate.

Who writes it: the orchestrator (/ship-feature, /audit), and only right after the owner said yes
in that same conversation, quoting what they said. Silence, "looks fine?" from an agent, or an
approval inferred from earlier work is not an approval. Only the owner's approvals go here.

What a client did (accepted the quote and statement of work, a spec, a change request, the
delivery) is not an owner approval: it is recorded in the Foundry HQ's private order file with
who at the client, when, how and the reference: `python3 tools/order.py accept <order> ...`
(run in the HQ). `--by client` is refused here and says so. For a `client` app the owner still
approves every gate here, and the client's acceptance is a separate gate beside it.

What it is never for: the legal sign-off. `comply`, `legal` and `signoff` are refused here: that
is `legal_gate.py sign`, run by a person in a terminal. The tax sign-off is the `## Sign-off`
section of docs/business/case.md, signed by the owner or an accountant.

One JSON object per line: {ts, gate, spec?, by, words, recorded_by, note?}. `recorded_by` is
`terminal` when run from an interactive terminal and `agent` otherwise. The Foundry workspace
shows it on the gate ("you · 11 Nov" with the words); a gate passed without a line here is shown
as "approval not recorded". Stdlib only. Writes only that one file.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

GATES = ["case", "define", "design", "architect", "plan", "release", "decision"]
REFUSED = {"comply", "legal", "signoff", "sign-off", "tax"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("app", type=Path)
    ap.add_argument("gate")
    ap.add_argument("--words", required=True, help="what the owner said, quoted verbatim")
    ap.add_argument("--spec", default=None)
    ap.add_argument("--by", choices=["owner", "client"], default="owner")
    ap.add_argument("--note", default=None)
    a = ap.parse_args(argv)
    gate = a.gate.strip().lower()
    if a.by == "client":
        print("refused: a client's acceptance is not an owner approval. Record it in the Foundry HQ with "
              "`python3 tools/order.py accept <order> quote|spec|delivery|change --who ... --on ... --how ... "
              "--ref ...` (who at the client, when, how, the reference).", file=sys.stderr)
        return 3
    if gate in REFUSED:
        print("refused: a legal or tax sign-off is not an ordinary gate. The owner or a lawyer runs "
              "`python3 docs/foundry/tooling/legal_gate.py sign . --by \"<name>\" --role owner|lawyer` "
              "in a terminal; nothing here records it.", file=sys.stderr)
        return 3
    if gate not in GATES:
        print(f"unknown gate {gate!r}; one of: {', '.join(GATES)}", file=sys.stderr)
        return 2
    words = " ".join(a.words.split())
    if len(words) < 2 or len(words) > 500:
        print("--words must quote what the owner said (2 to 500 characters)", file=sys.stderr)
        return 2
    if not (a.app / "docs").is_dir():
        print(f"not an app with a docs/ folder: {a.app}", file=sys.stderr)
        return 2
    log = a.app / "docs" / "foundry" / "approvals.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    e = {"ts": datetime.now().isoformat(timespec="seconds"), "gate": gate, "by": a.by, "words": words,
         "recorded_by": "terminal" if sys.stdin.isatty() else "agent"}
    if a.spec:
        e["spec"] = a.spec
    if a.note:
        e["note"] = a.note
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"recorded {gate} ({a.by}) -> {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
