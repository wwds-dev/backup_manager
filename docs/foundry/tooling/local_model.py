#!/usr/bin/env python3
"""One call to a local model: an OpenAI-compatible chat endpoint on this machine (LM Studio's local
server), never a cloud model.

    python3 docs/foundry/tooling/local_model.py --model <id> --prompt "<text>" [--system TEXT]
            [--prompt-file F] [--base-url URL] [--timeout S] [--max-tokens N] [--temperature T]
            [--purpose draft|eval|review|other] [--app .] [--json]
    python3 docs/foundry/tooling/local_model.py --list          # the models the server offers
    echo "<text>" | python3 docs/foundry/tooling/local_model.py --model <id>

Endpoint: --base-url, else LOCAL_MODEL_URL, else http://127.0.0.1:1234/v1. Model: --model, else
LOCAL_MODEL. LM Studio's docs (lmstudio.ai/docs/developer/openai-compat, read 2026-11-11) give
`http://localhost:1234/v1` as the base URL for OpenAI clients, list GET /v1/models and POST
/v1/chat/completions among its endpoints, and `lms server start --bind` defaults to 127.0.0.1;
the port is whatever the server was last started on (1234 in every example), so pass --base-url
when you changed it. If the server requires an API token (off by default; LM Studio 0.4.0+), set
LM_API_TOKEN: it is sent only to the loopback address.

Rules it enforces:
- Loopback only. The host must be 127.0.0.0/8, ::1 or `localhost` (sent to 127.0.0.1); any other
  host is refused before anything is sent. Proxies from the environment are ignored and redirects
  are not followed, so a request cannot leave the machine through either.
- Fails closed. When the server is not running, not reachable or answers with an error, it exits
  non-zero with a message and prints no reply. It never falls back to a cloud model.
- A timeout (default 120 s) bounds every request.
- Every successful call is counted: model, token counts and duration are appended to the app's
  docs/foundry/model_use.jsonl (model_use.py) with cost 0, so the workspace shows local work as
  zero-cost but counted. The prompt and the reply are not logged.

A local model drafts; it never decides. Its output is accepted only after the same checks as any
other work (AGENTS.md, "Local models"). Exit codes: 0 ok, 2 usage, 3 refused host, 4 server not
running or unreachable, 5 server error or bad answer, 6 timeout. Stdlib only.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_use  # noqa: E402

DEFAULT_URL = "http://127.0.0.1:1234/v1"


class Refused(Exception):
    """The endpoint is not on this machine."""


class ServerDown(Exception):
    """Nothing answers at the endpoint (or it is unreachable)."""


class ServerError(Exception):
    """The server answered, but with an error or something that is not a chat completion."""


def loopback_url(url: str) -> str:
    """The URL to call, or Refused. Only http(s) to a loopback address; `localhost` is pinned to
    127.0.0.1 so a hosts-file entry or a resolver cannot send it elsewhere."""
    u = urllib.parse.urlsplit(url.strip())
    if u.scheme not in ("http", "https"):
        raise Refused(f"only http or https to this machine, not {u.scheme or 'no scheme'!r}: {url}")
    if u.username or u.password:
        raise Refused("credentials in the URL are not accepted; use LM_API_TOKEN")
    host = (u.hostname or "").lower()
    if host == "localhost":
        netloc = "127.0.0.1" + (f":{u.port}" if u.port else "")
        return urllib.parse.urlunsplit((u.scheme, netloc, u.path, u.query, ""))
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        raise Refused(f"{host or 'no host'!r} is not a loopback address: a local model runs on this machine "
                      "(127.0.0.1, ::1 or localhost). Nothing was sent.") from None
    if not ip.is_loopback:
        raise Refused(f"{host} is not a loopback address. Nothing was sent; this tool never calls a remote model.")
    return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, u.query, ""))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise ServerError(f"the server redirected to {newurl}; redirects are not followed")


def _opener():
    # ProxyHandler({}) drops HTTP(S)_PROXY from the environment: a proxy would take the request off
    # this machine even for a loopback URL.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _request(base: str, path: str, body: dict | None, timeout: float) -> dict:
    url = loopback_url(base).rstrip("/") + path
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("LM_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    try:
        with _opener().open(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace") if e.fp else ""
        raise ServerError(f"the server answered HTTP {e.code}: {detail.strip() or e.reason}") from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise TimeoutError(str(e.reason)) from None
        raise ServerDown(str(e.reason)) from None
    except (ConnectionError, OSError) as e:
        if isinstance(e, (TimeoutError, socket.timeout)):
            raise TimeoutError(str(e)) from None
        raise ServerDown(str(e)) from None
    try:
        out = json.loads(raw)
    except ValueError:
        raise ServerError("the server's answer is not JSON") from None
    if not isinstance(out, dict):
        raise ServerError("the server's answer is not a JSON object")
    return out


def list_models(base: str, timeout: float = 10) -> list[str]:
    out = _request(base, "/models", None, timeout)
    return [m.get("id") for m in out.get("data") or [] if isinstance(m, dict) and m.get("id")]


def chat(base: str, model: str, prompt: str, system: str | None = None, timeout: float = 120,
         max_tokens: int | None = None, temperature: float | None = None) -> dict:
    """One chat completion. Returns {text, model, input_tokens, output_tokens, seconds, raw}."""
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": model, "messages": msgs, "stream": False}
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    if temperature is not None:
        body["temperature"] = temperature
    t0 = time.monotonic()
    out = _request(base, "/chat/completions", body, timeout)
    seconds = time.monotonic() - t0
    try:
        text = out["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ServerError("the answer has no choices[0].message.content") from None
    if not isinstance(text, str):
        raise ServerError("the reply is not text")
    usage = out.get("usage") if isinstance(out.get("usage"), dict) else {}
    tok = lambda k: usage.get(k) if isinstance(usage.get(k), int) and usage.get(k) >= 0 else None  # noqa: E731
    return {"text": text, "model": out.get("model") or model, "input_tokens": tok("prompt_tokens"),
            "output_tokens": tok("completion_tokens"), "seconds": seconds, "raw": out}


DOWN_HELP = ("Start LM Studio's server (Developer tab > Start server, or `lms server start`), load a model, "
             "and pass --base-url if it is not on port 1234. Nothing was sent to any other model.")


def main(argv: list[str] | None = None, stdin=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-url", default=os.environ.get("LOCAL_MODEL_URL") or DEFAULT_URL)
    ap.add_argument("--model", default=os.environ.get("LOCAL_MODEL"))
    ap.add_argument("--prompt")
    ap.add_argument("--prompt-file", type=Path)
    ap.add_argument("--system")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--max-tokens", type=int)
    ap.add_argument("--temperature", type=float)
    ap.add_argument("--purpose", choices=model_use.PURPOSES, default="draft")
    ap.add_argument("--app", type=Path, default=Path("."), help="the app whose model_use.jsonl counts the call")
    ap.add_argument("--json", action="store_true", help="print the server's whole answer")
    ap.add_argument("--list", action="store_true", help="list the models the server offers")
    a = ap.parse_args(argv)
    if a.timeout <= 0:
        print("--timeout must be above 0", file=sys.stderr)
        return 2
    try:
        loopback_url(a.base_url)
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 3
    try:
        if a.list:
            for m in list_models(a.base_url, min(a.timeout, 10)):
                print(m)
            return 0
        if not a.model:
            print("no model: pass --model <id> or set LOCAL_MODEL (see --list)", file=sys.stderr)
            return 2
        if a.prompt is not None:
            prompt = a.prompt
        elif a.prompt_file:
            prompt = a.prompt_file.read_text(encoding="utf-8")
        else:
            src = stdin or sys.stdin
            prompt = "" if src.isatty() else src.read()
        if not prompt.strip():
            print("no prompt: pass --prompt, --prompt-file or pipe text in", file=sys.stderr)
            return 2
        r = chat(a.base_url, a.model, prompt, a.system, a.timeout, a.max_tokens, a.temperature)
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 3
    except ServerDown as e:
        print(f"local model server not reachable at {a.base_url} ({e}). {DOWN_HELP}", file=sys.stderr)
        return 4
    except TimeoutError:
        print(f"no answer within {a.timeout:g} s from {a.base_url}; raise --timeout or use a smaller model. "
              "Nothing was sent to any other model.", file=sys.stderr)
        return 6
    except ServerError as e:
        print(f"local model server error: {e}", file=sys.stderr)
        return 5
    print(json.dumps(r["raw"], indent=1, ensure_ascii=False) if a.json else r["text"])
    try:
        model_use.record(a.app, "local", r["model"], r["input_tokens"], r["output_tokens"], r["seconds"],
                         purpose=a.purpose)
    except (FileNotFoundError, OSError, ValueError) as e:
        print(f"note: call not counted ({e}); pass --app <app folder>", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
