"""Secure follow-ups P3-4, P3-5, P3-6 (spec more-storage-providers). No network."""

from __future__ import annotations

import os
import stat
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cloud_quota  # noqa: E402
import main  # noqa: E402


def test_set_token_entry_waits_for_refresh_in_flight():
    """P3-4: a connect must not interleave with a refresh that holds the account lock."""
    lock = cloud_quota._refresh_lock("acct")
    done = threading.Event()
    t = threading.Thread(target=lambda: (cloud_quota._set_token_entry("acct", {"refresh_token": "new"}),
                                         done.set()), daemon=True)
    with lock:
        t.start()
        assert not done.wait(0.3)  # blocked while the refresh holds the lock
    assert done.wait(2)
    assert cloud_quota.load_tokens()["acct"]["refresh_token"] == "new"


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


def test_negative_used_clamped_onedrive(monkeypatch):
    cloud_quota._set_token_entry("od", {"refresh_token": "rt"})
    monkeypatch.setattr(cloud_quota, "_onedrive_access_token", lambda k: "at")
    monkeypatch.setattr(cloud_quota.requests, "get",
                        lambda *a, **k: _Resp({"quota": {"used": -5, "total": 10}}))
    assert cloud_quota.onedrive_quota("od") == (0, 10)


def test_negative_used_clamped_google_and_dropbox(monkeypatch):
    cloud_quota._set_token_entry("g", {"refresh_token": "rt"})
    monkeypatch.setattr(cloud_quota, "_google_access_token", lambda rt: "at")
    monkeypatch.setattr(cloud_quota.requests, "get",
                        lambda *a, **k: _Resp({"storageQuota": {"usage": "-7", "limit": "10"}}))
    assert tuple(cloud_quota.google_quota("g")) == (0, 10)
    monkeypatch.setattr(cloud_quota, "_dropbox_access_token", lambda rt: "at")
    monkeypatch.setattr(cloud_quota.requests, "post",
                        lambda *a, **k: _Resp({"used": -7, "allocation": {"allocated": 10}}))
    assert cloud_quota.dropbox_quota("g") == (0, 10)


def test_quota_history_written_atomically_0600(monkeypatch, tmp_path):
    """P3-6: history goes through the atomic writer into a 0700 folder."""
    d = tmp_path / "fresh"
    monkeypatch.setattr(cloud_quota, "SECRETS_DIR", d)
    monkeypatch.setattr(main, "_QUOTA_HISTORY_FILE", d / "quota_history.json")
    calls = []
    real = cloud_quota._write_json_atomic
    monkeypatch.setattr(cloud_quota, "_write_json_atomic",
                        lambda p, data: (calls.append(p), real(p, data))[1])
    main._append_quota_sample("k", 1, 2)
    assert calls == [d / "quota_history.json"]
    assert stat.S_IMODE(os.stat(d / "quota_history.json").st_mode) == 0o600
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o700
    assert main._get_quota_history("k")[0]["used"] == 1
