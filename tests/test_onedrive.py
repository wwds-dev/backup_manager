"""OneDrive provider (spec more-storage-providers, step 3).

PKCE public client (no secret), `state` checked on the redirect, rotated refresh token stored
atomically (0600) under a lock, quota from Graph `/me/drive?$select=quota`. No network: every
HTTP call is a fake.
"""

from __future__ import annotations

import json
import os
import stat
import threading
import time
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

import cloud_quota  # noqa: E402
import main  # noqa: E402

KEY = "OneDrive-Personal"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(cloud_quota, "SECRETS_DIR", tmp_path)
    monkeypatch.setattr(cloud_quota, "CREDENTIALS_FILE", tmp_path / "app_credentials.json")
    monkeypatch.setattr(cloud_quota, "TOKENS_FILE", tmp_path / "tokens.json")
    monkeypatch.setattr(cloud_quota, "MANUAL_ACCOUNTS_FILE", tmp_path / "manual_accounts.json")
    monkeypatch.setattr(main, "_QUOTA_HISTORY_FILE", tmp_path / "quota_history.json")

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
            raise requests.HTTPError(f"{self.status_code} Client Error: Bad Request for url: x")


def _save_client_id():
    cloud_quota.save_app_credentials({"onedrive": {"client_id": "cid-123"}})


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


# ---------------------------------------------------------------------------- registry
def test_registry_entry():
    p = cloud_quota.PROVIDERS["onedrive"]
    assert p.label == "OneDrive" and p.has_quota
    assert p.web_url.startswith("https://")
    assert [f[0] for f in p.credential_fields] == ["client_id"]  # public client: no secret
    assert not any(secret for _f, _l, secret in p.credential_fields)


@pytest.mark.parametrize("name", ["OneDrive-Personal", "OneDrive-Contoso Ltd", "onedrive-x"])
def test_mount_prefix(name):
    assert cloud_quota.provider_for_name(name) == "onedrive"


def test_split_tile_name():
    assert main.split_tile_name("OneDrive-Personal") == ("OneDrive", "Personal")


# ---------------------------------------------------------------------------- connect
def _connect(monkeypatch, *, state_override=None, token_resp=None):
    _save_client_id()
    seen = {}

    def fake_open(url):
        seen["auth_url"] = url
        return True

    def fake_wait(port, timeout=180):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(seen["auth_url"]).query)
        state = q["state"][0] if state_override is None else state_override
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
    return cloud_quota.connect("onedrive", KEY), seen


def test_connect_without_client_id():
    ok, err = cloud_quota.connect("onedrive", KEY)
    assert not ok and "Client ID" in err


def test_connect_happy_path(monkeypatch):
    (ok, err), seen = _connect(monkeypatch)
    assert ok, err
    q = urllib.parse.parse_qs(urllib.parse.urlparse(seen["auth_url"]).query)
    assert seen["auth_url"].startswith("https://login.microsoftonline.com/common/oauth2/v2.0/authorize")
    assert q["client_id"] == ["cid-123"]
    assert q["code_challenge_method"] == ["S256"] and q["code_challenge"][0]
    assert "offline_access" in q["scope"][0] and "Files.Read" in q["scope"][0]
    assert len(q["state"][0]) >= 32
    url, data = seen["posts"][0]
    assert url == "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    assert data["grant_type"] == "authorization_code"
    assert data["code"] == "the-auth-code" and data["code_verifier"]
    assert "client_secret" not in data
    tokens = cloud_quota.load_tokens()
    assert tokens[KEY] == {"provider": "onedrive", "refresh_token": "rt-1"}
    assert _mode(cloud_quota.TOKENS_FILE) == 0o600


@pytest.mark.parametrize("bad_state", ["wrong-state", "", False])
def test_connect_rejects_bad_or_missing_state(monkeypatch, bad_state):
    (ok, err), seen = _connect(monkeypatch, state_override=bad_state)
    assert not ok and "state" in err.lower()
    assert "posts" not in seen  # the code is never exchanged
    assert KEY not in cloud_quota.load_tokens()


def test_connect_failure_text_does_not_echo_code(monkeypatch):
    (ok, err), _ = _connect(monkeypatch, token_resp=Resp(400, {
        "error": "invalid_grant", "error_description": "AADSTS70000: bad code the-auth-code"}))
    assert not ok
    assert "invalid_grant" in err
    assert "the-auth-code" not in err


def test_connect_without_refresh_token(monkeypatch):
    (ok, err), _ = _connect(monkeypatch, token_resp=Resp(200, {"access_token": "at"}))
    assert not ok and "refresh token" in err.lower()


def test_redirect_with_error_param_is_reported(monkeypatch):
    _save_client_id()
    monkeypatch.setattr(cloud_quota.webbrowser, "open", lambda url: True)
    monkeypatch.setattr(cloud_quota, "_wait_for_redirect",
                        lambda port, timeout=180: {"error": ["access_denied"]})
    ok, err = cloud_quota.connect("onedrive", KEY)
    assert not ok


# ---------------------------------------------------------------------------- rotation
def _stored(rt):
    cloud_quota.save_tokens({KEY: {"provider": "onedrive", "refresh_token": rt},
                             "other": {"provider": "google", "refresh_token": "g"}})


def test_refresh_stores_rotated_token_atomically(monkeypatch, tmp_path):
    _save_client_id()
    _stored("rt-old")
    os.chmod(cloud_quota.TOKENS_FILE, 0o644)  # a loose old file is tightened by the rewrite
    sent = []

    def fake_post(url, data=None, **k):
        sent.append(dict(data))
        return Resp(200, {"access_token": "at", "refresh_token": "rt-new"})
    monkeypatch.setattr(cloud_quota.requests, "post", fake_post)
    assert cloud_quota._onedrive_access_token(KEY) == "at"
    assert sent[0]["refresh_token"] == "rt-old" and "client_secret" not in sent[0]
    tokens = cloud_quota.load_tokens()
    assert tokens[KEY] == {"provider": "onedrive", "refresh_token": "rt-new"}
    assert tokens["other"]["refresh_token"] == "g"
    assert _mode(cloud_quota.TOKENS_FILE) == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["app_credentials.json", "tokens.json"]


def test_refresh_without_new_token_keeps_old(monkeypatch):
    _save_client_id()
    _stored("rt-old")
    monkeypatch.setattr(cloud_quota.requests, "post",
                        lambda url, data=None, **k: Resp(200, {"access_token": "at"}))
    cloud_quota._onedrive_access_token(KEY)
    assert cloud_quota.load_tokens()[KEY]["refresh_token"] == "rt-old"


def test_atomic_write_never_leaves_a_partial_file(monkeypatch):
    _stored("rt-old")
    before = cloud_quota.TOKENS_FILE.read_text()

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(cloud_quota.os, "replace", boom)
    with pytest.raises(OSError):
        cloud_quota._store_refresh_token(KEY, "rt-new")
    assert cloud_quota.TOKENS_FILE.read_text() == before
    assert [p.name for p in cloud_quota.SECRETS_DIR.iterdir()] == ["tokens.json"]


def test_overlapping_refreshes_use_the_rotated_token(monkeypatch):
    """A single-use refresh token: the second refresh must send the token the first stored."""
    _save_client_id()
    _stored("rt-0")
    state = {"valid": "rt-0", "n": 0}
    lock = threading.Lock()

    def fake_post(url, data=None, **k):
        time.sleep(0.05)  # widen the window two unlocked refreshes would race in
        with lock:
            if data["refresh_token"] != state["valid"]:
                return Resp(400, {"error": "invalid_grant"})
            state["n"] += 1
            state["valid"] = f"rt-{state['n']}"
            return Resp(200, {"access_token": f"at-{state['n']}", "refresh_token": state["valid"]})
    monkeypatch.setattr(cloud_quota.requests, "post", fake_post)
    errors = []

    def run():
        try:
            cloud_quota._onedrive_access_token(KEY)
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=run) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert errors == []
    assert cloud_quota.load_tokens()[KEY]["refresh_token"] == "rt-3"


# ---------------------------------------------------------------------------- quota
def _quota(monkeypatch, status, body):
    _save_client_id()
    _stored("rt")
    monkeypatch.setattr(cloud_quota, "_onedrive_access_token", lambda key: "at")
    seen = {}

    def fake_get(url, params=None, headers=None, **k):
        seen.update(url=url, params=params, headers=headers)
        return Resp(status, body)
    monkeypatch.setattr(cloud_quota.requests, "get", fake_get)
    return seen


def test_quota_reads_graph(monkeypatch):
    seen = _quota(monkeypatch, 200, {"quota": {"used": 10, "total": 100, "remaining": 90,
                                               "deleted": 1, "state": "normal"}})
    q = cloud_quota.quota(KEY)
    assert q == (10, 100)
    assert seen["url"] == "https://graph.microsoft.com/v1.0/me/drive"
    assert seen["params"] == {"$select": "quota"}
    assert seen["headers"]["Authorization"] == "Bearer at"


def test_quota_without_total(monkeypatch):
    _quota(monkeypatch, 200, {"quota": {"used": 10}})
    assert cloud_quota.quota(KEY) == (10, None)


def test_quota_401_raises_with_status(monkeypatch):
    _quota(monkeypatch, 401, {"error": {"code": "InvalidAuthenticationToken"}})
    with pytest.raises(requests.HTTPError, match="401"):
        cloud_quota.quota(KEY)


# ---------------------------------------------------------------------------- tile / gauge
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _settle(tile):
    w = tile._quota_worker
    if w is not None:
        assert w.wait(5000)
    QApplication.processEvents()
    return tile


def test_tile_renders_used_of_total(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(main.cloud_quota, "is_connected", lambda k: True)
    monkeypatch.setattr(main.cloud_quota, "quota", lambda k: cloud_quota.Quota(25 * 10**9, 100 * 10**9))
    tile = _settle(main.StorageTile(KEY, tmp_path, True))
    assert tile.provider == "onedrive"
    assert "used of" in tile.detail_lbl.text() and "account quota" in tile.detail_lbl.text()
    assert tile.pct == 25


def test_tile_failed_call_never_shows_local_disk(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(main.cloud_quota, "is_connected", lambda k: True)

    def boom(k):
        raise RuntimeError("503 Service Unavailable")
    monkeypatch.setattr(main.cloud_quota, "quota", boom)
    tile = _settle(main.StorageTile(KEY, tmp_path, True))
    assert "local disk" not in tile.detail_lbl.text()
    assert tile.pct is None


def test_tile_401_shows_reconnect(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(main.cloud_quota, "is_connected", lambda k: True)

    def boom(k):
        raise requests.HTTPError("401 Client Error")
    monkeypatch.setattr(main.cloud_quota, "quota", boom)
    tile = _settle(main.StorageTile(KEY, tmp_path, True))
    assert not tile.reconnect_btn.isHidden()


def test_mounted_unconnected_tile_has_connect_link(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(main.cloud_quota, "is_connected", lambda k: False)
    tile = main.StorageTile(KEY, tmp_path, True)
    texts = [b.text() for b in tile.findChildren(main.QPushButton)]
    assert any("Connect for account quota" in t for t in texts)


class FakeTile:
    def __init__(self, provider, pct, detail):
        self.provider = provider
        self.pct = pct
        self.account_key = ""
        self.detail_lbl = QLabel(detail)
        self.account_lbl = QLabel("")


def _page(tiles):
    window = SimpleNamespace(
        backup_card=SimpleNamespace(proc=None, _dry_run=False),
        tm_card=SimpleNamespace(state={"configured": None}),
        storage_card=SimpleNamespace(tiles=tiles),
    )
    return main.OverviewPage(window)


def test_no_onedrive_gauge_without_account(qapp):
    page = _page([FakeTile("google", 10, "x")])
    page.refresh_gauges()
    assert "onedrive" not in page.gauges or page.gauges["onedrive"].isHidden()
    assert list(page.gauges)[:4] == ["disk", "google", "dropbox", "icloud"]


def test_onedrive_gauge_appears_with_account(qapp):
    tiles = [FakeTile("google", 10, "x")]
    page = _page(tiles)
    page.refresh_gauges()
    tiles.append(FakeTile("onedrive", 37, "37 used"))
    page.refresh_gauges()
    g = page.gauges["onedrive"]
    assert not g.isHidden()
    assert g.value_lbl.text() == "37 %"
    page.refresh_gauges()  # a second refresh does not add another column
    assert list(page.gauges).count("onedrive") == 1
    tiles.pop()
    page.refresh_gauges()
    assert g.isHidden()  # account removed: the slot goes away again
