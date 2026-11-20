"""OAuth and secrets-file hardening (Secure pass, spec more-storage-providers,
docs/audit/more-storage-providers-secure.md P2-1, P2-2, P2-3, P3-1, P3-2).

No provider is ever called: HTTP is faked, and the redirect-listener tests use a real
loopback socket only.
"""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.parse

import pytest
import requests

import cloud_quota

KEY = "acct"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(cloud_quota, "SECRETS_DIR", tmp_path)
    monkeypatch.setattr(cloud_quota, "CREDENTIALS_FILE", tmp_path / "app_credentials.json")
    monkeypatch.setattr(cloud_quota, "TOKENS_FILE", tmp_path / "tokens.json")
    monkeypatch.setattr(cloud_quota, "MANUAL_ACCOUNTS_FILE", tmp_path / "manual_accounts.json")

    def no_network(*a, **k):
        raise AssertionError("unexpected network call")
    monkeypatch.setattr(cloud_quota.requests, "get", no_network)
    monkeypatch.setattr(cloud_quota.requests, "post", no_network)
    monkeypatch.setattr(cloud_quota.webbrowser, "open", no_network)


class Resp:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


CREDS = {"google": {"client_id": "gid", "client_secret": "gsecret"},
         "dropbox": {"app_key": "dkey", "app_secret": "dsecret"}}


def _connect(monkeypatch, provider, *, state_override=None, token_resp=None):
    """Run google/dropbox connect with a fake browser, redirect and token endpoint.
    state_override: None echoes the request's state, False omits it, a string replaces it."""
    cloud_quota.save_app_credentials(CREDS)
    seen = {}

    def fake_open(url):
        seen["auth_url"] = url
        return True

    def fake_wait(port, timeout=180):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(seen["auth_url"]).query)
        state = (q.get("state") or [""])[0] if state_override is None else state_override
        result = {"code": ["the-auth-code"]}
        if state is not False:
            result["state"] = [state]
        return result

    def fake_post(url, data=None, **k):
        seen.setdefault("posts", []).append((url, dict(data)))
        return token_resp or Resp(200, {"access_token": "at", "refresh_token": "rt-1"})

    monkeypatch.setattr(cloud_quota.webbrowser, "open", fake_open)
    monkeypatch.setattr(cloud_quota, "_wait_for_redirect", fake_wait)
    monkeypatch.setattr(cloud_quota.requests, "post", fake_post)
    return cloud_quota.connect(provider, KEY), seen


def _auth_query(seen):
    return urllib.parse.parse_qs(urllib.parse.urlparse(seen["auth_url"]).query)


# ---------------------------------------------------------------------------- P2-1 state + PKCE
@pytest.mark.parametrize("provider", ["google", "dropbox"])
def test_connect_sends_state_and_succeeds_when_it_matches(monkeypatch, provider):
    (ok, err), seen = _connect(monkeypatch, provider)
    assert ok, err
    assert len(_auth_query(seen)["state"][0]) >= 32
    assert seen["posts"][0][1]["code"] == "the-auth-code"
    assert cloud_quota.load_tokens()[KEY]["provider"] == provider


@pytest.mark.parametrize("provider", ["google", "dropbox"])
@pytest.mark.parametrize("bad_state", ["wrong-state", "", False])
def test_connect_rejects_bad_or_missing_state(monkeypatch, provider, bad_state):
    (ok, err), seen = _connect(monkeypatch, provider, state_override=bad_state)
    assert not ok and "state" in err.lower()
    assert "posts" not in seen  # the code is never exchanged
    assert KEY not in cloud_quota.load_tokens()


def test_state_differs_per_attempt(monkeypatch):
    _, a = _connect(monkeypatch, "google")
    _, b = _connect(monkeypatch, "google")
    assert _auth_query(a)["state"] != _auth_query(b)["state"]


def _s256(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


@pytest.mark.parametrize("provider", ["google", "dropbox"])
def test_connect_uses_pkce_s256_and_sends_the_verifier(monkeypatch, provider):
    (ok, err), seen = _connect(monkeypatch, provider)
    assert ok, err
    q = _auth_query(seen)
    assert q["code_challenge_method"] == ["S256"]
    verifier = seen["posts"][0][1]["code_verifier"]
    assert len(verifier) >= 43
    assert q["code_challenge"] == [_s256(verifier)]


# ---------------------------------------------------------------------------- P2-2 / P3-2 listener
import socket  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_wait(port, timeout):
    """Run _wait_for_redirect in a thread; return (thread, box) once the port accepts."""
    box = {}

    def run():
        box["result"] = cloud_quota._wait_for_redirect(port, timeout=timeout)
        box["at"] = time.monotonic()
    t = threading.Thread(target=run, daemon=True)
    t.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.02)
    return t, box


def _get(port, path):
    with socket.create_connection(("127.0.0.1", port), timeout=3) as s:
        s.sendall(f"GET {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode())
        return s.recv(4096)


def test_stalled_connection_does_not_block_the_real_redirect():
    port = _free_port()
    t, box = _start_wait(port, timeout=10)
    stalled = socket.create_connection(("127.0.0.1", port))  # connects, sends nothing
    try:
        reply = _get(port, "/?code=c1&state=s1")
        assert b"200" in reply.split(b"\r\n")[0]
        t.join(5)
        assert not t.is_alive(), "wait did not return while a stalled connection was open"
        assert box["result"]["code"] == ["c1"]
    finally:
        stalled.close()


def test_stalled_connection_does_not_hold_the_wait_past_its_timeout():
    port = _free_port()
    t, box = _start_wait(port, timeout=1)
    stalled = socket.create_connection(("127.0.0.1", port))
    try:
        t0 = time.monotonic()
        t.join(6)
        assert not t.is_alive(), "wait hung on the stalled connection"
        assert box["at"] - t0 < 4
        assert box["result"] == {}
    finally:
        stalled.close()


def test_port_is_free_again_after_a_stalled_wait():
    port = _free_port()
    t, _ = _start_wait(port, timeout=0.5)
    stalled = socket.create_connection(("127.0.0.1", port))
    try:
        t.join(6)
        assert not t.is_alive()
        t2, box2 = _start_wait(port, timeout=5)  # a second connect can rebind
        _get(port, "/?code=c2&state=s2")
        t2.join(5)
        assert box2["result"]["code"] == ["c2"]
    finally:
        stalled.close()


@pytest.mark.parametrize("stray", ["/favicon.ico", "/", "/?foo=bar"])
def test_request_without_code_or_error_is_ignored(stray):
    port = _free_port()
    t, box = _start_wait(port, timeout=10)
    _get(port, stray)
    time.sleep(0.2)
    assert t.is_alive(), "a stray request ended the wait"
    _get(port, "/?code=c3&state=s3")
    t.join(5)
    assert box["result"]["code"] == ["c3"] and box["result"]["state"] == ["s3"]


def test_error_redirect_ends_the_wait():
    port = _free_port()
    t, box = _start_wait(port, timeout=10)
    _get(port, "/?error=access_denied&state=s4")
    t.join(5)
    assert not t.is_alive()
    assert box["result"]["error"] == ["access_denied"]


# ---------------------------------------------------------------------------- P2-3 secrets files
import os  # noqa: E402
import stat  # noqa: E402


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


@pytest.fixture
def fresh_dir(monkeypatch, tmp_path):
    """SECRETS_DIR not created yet, files inside it, umask 022 (the macOS default)."""
    sd = tmp_path / "sd"
    monkeypatch.setattr(cloud_quota, "SECRETS_DIR", sd)
    monkeypatch.setattr(cloud_quota, "CREDENTIALS_FILE", sd / "app_credentials.json")
    monkeypatch.setattr(cloud_quota, "TOKENS_FILE", sd / "tokens.json")
    monkeypatch.setattr(cloud_quota, "MANUAL_ACCOUNTS_FILE", sd / "manual_accounts.json")
    old = os.umask(0o022)
    yield sd
    os.umask(old)


WRITERS = {
    "credentials": (lambda: cloud_quota.save_app_credentials(CREDS),
                    lambda: cloud_quota.CREDENTIALS_FILE),
    "manual": (lambda: cloud_quota.save_manual_accounts([{"key": "k", "provider": "proton", "label": "x"}]),
               lambda: cloud_quota.MANUAL_ACCOUNTS_FILE),
    "tokens": (lambda: cloud_quota.save_tokens({KEY: {"provider": "google", "refresh_token": "r"}}),
               lambda: cloud_quota.TOKENS_FILE),
}


@pytest.mark.parametrize("which", list(WRITERS))
def test_new_folder_is_0700_and_file_0600(fresh_dir, which):
    write, path = WRITERS[which]
    write()
    assert _mode(fresh_dir) == 0o700
    assert _mode(path()) == 0o600


@pytest.mark.parametrize("which", list(WRITERS))
def test_existing_loose_folder_and_file_are_tightened(fresh_dir, which):
    write, path = WRITERS[which]
    fresh_dir.mkdir(mode=0o755)
    os.chmod(fresh_dir, 0o755)
    path().write_text("{}")
    os.chmod(path(), 0o644)
    write()
    assert _mode(fresh_dir) == 0o700
    assert _mode(path()) == 0o600


@pytest.mark.parametrize("which", list(WRITERS))
def test_file_is_0600_before_it_takes_the_real_name(fresh_dir, monkeypatch, which):
    write, path = WRITERS[which]
    real_replace = os.replace
    seen = []

    def spy(src, dst):
        seen.append((_mode(src), json.loads(open(src).read())))
        return real_replace(src, dst)
    monkeypatch.setattr(cloud_quota.os, "replace", spy)
    write()
    assert seen and seen[0][0] == 0o600 and seen[0][1]  # complete content, already private


@pytest.mark.parametrize("which", list(WRITERS))
def test_failed_replace_leaves_the_old_file(fresh_dir, monkeypatch, which):
    write, path = WRITERS[which]
    fresh_dir.mkdir(mode=0o700)
    path().write_text('{"old": true}')

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(cloud_quota.os, "replace", boom)
    with pytest.raises(OSError):
        write()
    assert json.loads(path().read_text()) == {"old": True}
    assert [p.name for p in fresh_dir.iterdir()] == [path().name]  # no temp file left


# ---------------------------------------------------------------------------- P3-1 error text
@pytest.mark.parametrize("provider", ["google", "dropbox"])
def test_token_exchange_error_shows_the_error_code_only(monkeypatch, provider):
    body = {"error": "invalid_grant",
            "error_description": "Bad code the-auth-code for secret gsecret dsecret"}
    (ok, err), _ = _connect(monkeypatch, provider, token_resp=Resp(400, body))
    assert not ok
    assert "invalid_grant" in err and "400" in err
    for leaked in ("the-auth-code", "gsecret", "dsecret", "Bad code", "error_description"):
        assert leaked not in err


@pytest.mark.parametrize("provider", ["google", "dropbox"])
def test_token_exchange_error_with_a_non_json_body(monkeypatch, provider):
    class HtmlResp(Resp):
        def json(self):
            raise ValueError("not json")
    resp = HtmlResp(502, {})
    resp.text = "<html>upstream the-auth-code</html>"
    (ok, err), _ = _connect(monkeypatch, provider, token_resp=resp)
    assert not ok and "502" in err and "the-auth-code" not in err and "html" not in err


@pytest.mark.parametrize("body", [["a", "list"], {"error": "x" * 500}, {"error": "bad code: the-auth-code"},
                                  {"error": {"nested": "the-auth-code"}}])
def test_error_text_ignores_odd_error_fields(body):
    text = cloud_quota._oauth_error_text(Resp(400, body))
    assert text == "HTTP 400"


def test_first_sign_in_response_wins_over_a_later_one():
    port = _free_port()
    t, box = _start_wait(port, timeout=10)
    late = socket.create_connection(("127.0.0.1", port), timeout=3)
    try:
        late.sendall(b"GET /?code=late&state=late HTTP/1.0\r\n")  # headers not finished yet
        time.sleep(0.1)
        _get(port, "/?code=first&state=first")
        t.join(5)
        late.sendall(b"Host: localhost\r\n\r\n")  # the later response lands after the first
        late.recv(4096)
        time.sleep(0.1)
        assert box["result"]["code"] == ["first"] and box["result"]["state"] == ["first"]
    finally:
        late.close()
