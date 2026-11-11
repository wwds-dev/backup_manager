#!/usr/bin/env python3
"""Record one model run in the app's docs/foundry/model_use.jsonl (read by the Foundry workspace's
Time & money and the app page). Used by local_model.py for every local call, and by an app's live
eval suite (or a person) for a paid API run, so local work shows as counted and the eval spend
shows against the plan's eval budget.

    python3 docs/foundry/tooling/model_use.py . --provider local|anthropic|openai|<name> --model M
                [--input-tokens N] [--output-tokens N] [--seconds S] [--cost-usd X]
                [--purpose draft|eval|review|other] [--note TEXT]

One JSON object per line: {ts, provider, model, local, input_tokens?, output_tokens?, seconds?,
cost_usd?, purpose, note?}. A local run's cost is 0 because nothing is paid per token (the
machine's power is not counted); a paid run with no --cost-usd is "not recorded", never 0. The
prompt and the reply are never written here: they may hold client or personal data.
Stdlib only. Writes only that one file.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PURPOSES = ("draft", "eval", "review", "other")
LOG = Path("docs") / "foundry" / "model_use.jsonl"


def _nonneg_int(s: str) -> int:
    v = int(s)
    if v < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return v


def _nonneg(s: str) -> float:
    v = float(s)
    if v < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return v


def record(app: Path, provider: str, model: str, input_tokens: int | None = None,
           output_tokens: int | None = None, seconds: float | None = None, cost_usd: float | None = None,
           purpose: str = "other", note: str | None = None, now: datetime | None = None) -> Path:
    """Append one run. Raises FileNotFoundError when `app` has no docs/ folder."""
    if not (app / "docs").is_dir():
        raise FileNotFoundError(f"not an app with a docs/ folder: {app}")
    if purpose not in PURPOSES:
        raise ValueError(f"purpose must be one of {', '.join(PURPOSES)}")
    local = provider == "local"
    e = {"ts": (now or datetime.now()).isoformat(timespec="seconds"), "provider": provider, "model": model,
         "local": local, "purpose": purpose}
    for k, v in (("input_tokens", input_tokens), ("output_tokens", output_tokens),
                 ("seconds", round(seconds, 2) if seconds is not None else None)):
        if v is not None:
            e[k] = v
    if local:
        e["cost_usd"] = 0.0
    elif cost_usd is not None:
        e["cost_usd"] = round(cost_usd, 6)
    if note:
        e["note"] = " ".join(note.split())[:200]
    path = app / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("app", type=Path)
    ap.add_argument("--provider", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--input-tokens", type=_nonneg_int)
    ap.add_argument("--output-tokens", type=_nonneg_int)
    ap.add_argument("--seconds", type=_nonneg)
    ap.add_argument("--cost-usd", type=_nonneg)
    ap.add_argument("--purpose", choices=PURPOSES, default="other")
    ap.add_argument("--note")
    a = ap.parse_args(argv)
    try:
        p = record(a.app, a.provider.strip().lower(), a.model.strip(), a.input_tokens, a.output_tokens,
                   a.seconds, a.cost_usd, a.purpose, a.note)
    except (FileNotFoundError, ValueError) as err:
        print(err, file=sys.stderr)
        return 2
    print(f"recorded {a.provider} {a.model} -> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
