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
