"""A connected cloud tile must never show local-disk numbers when its quota call fails.

On 2026-11-20 every storage card showed the Mac disk's 348.8 GB free of 926.4 GB because
a quota call failed (not a 400/401) and `set_usage` fell through to the local-disk branch.
Now a failed call shows the last known sample "as of <time>", or "unavailable".
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import main  # noqa: E402

KEY = "GoogleDrive-someone@example.com"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(main.build_app_style(False))
    yield app


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No network, no writes to the user's real quota history."""
    monkeypatch.setattr(main.cloud_quota, "SECRETS_DIR", tmp_path)
    monkeypatch.setattr(main, "_QUOTA_HISTORY_FILE", tmp_path / "quota_history.json")
    monkeypatch.setattr(main.cloud_quota, "is_connected", lambda key: True)
    monkeypatch.setattr(main.cloud_quota, "dropbox_account_email", lambda key: None)


def _history(tmp_path, samples):
    (tmp_path / "quota_history.json").write_text(json.dumps({KEY: samples}))


def _tile(qapp):
    return main.StorageTile(KEY, Path.home(), True, provider_override="google",
                            display_account="someone@example.com")


def _fail(monkeypatch, exc=None):
    def boom(key):
        raise exc or RuntimeError("503 Service Unavailable")
    monkeypatch.setattr(main.cloud_quota, "quota", boom)


def test_failed_call_shows_last_known_sample_not_local_disk(qapp, monkeypatch, tmp_path):
    _history(tmp_path, [{"ts": "2026-11-19T09:05", "used": 44_000_000_000,
                         "total": 107_374_182_400}])
    _fail(monkeypatch)
    tile = _tile(qapp)
    text = tile.detail_lbl.text()
    assert "local disk" not in text and "free of" not in text
    assert "used of" in text and "as of" in text
    assert tile.pct == 40  # 44.0 / 107.37 from the sample, not the Mac disk
    assert tile.bar.value() == 40
    assert "as of 19 Nov 09:05" in text or "as of 09:05" in text


def test_failed_call_without_history_says_unavailable(qapp, monkeypatch):
    _fail(monkeypatch)
    tile = _tile(qapp)
    assert tile.detail_lbl.text() == "Account quota unavailable"
    assert tile.pct is None
    assert tile.bar.value() == 0


def test_quota_returning_nothing_is_treated_as_unavailable(qapp, monkeypatch):
    monkeypatch.setattr(main.cloud_quota, "quota", lambda key: None)
    tile = _tile(qapp)
    assert "local disk" not in tile.detail_lbl.text()
    assert tile.pct is None


def _gauge_page(tiles):
    from types import SimpleNamespace
    window = SimpleNamespace(
        backup_card=SimpleNamespace(proc=None, _dry_run=False),
        tm_card=SimpleNamespace(state={"configured": None}),
        storage_card=SimpleNamespace(tiles=tiles),
    )
    return main.OverviewPage(window)


def test_overview_gauge_shows_last_known_not_local_disk(qapp, monkeypatch, tmp_path):
    _history(tmp_path, [{"ts": "2026-11-19T09:05", "used": 1, "total": 2}])
    _fail(monkeypatch)
    page = _gauge_page([_tile(qapp)])
    page.refresh_gauges()
    g = page.gauges["google"]
    assert g.value_lbl.text() == "50 %"
    assert "as of" in g.detail_lbl.text() and "local disk" not in g.detail_lbl.text()


def test_overview_gauge_without_history_shows_dash(qapp, monkeypatch):
    _fail(monkeypatch)
    page = _gauge_page([_tile(qapp)])
    page.refresh_gauges()
    g = page.gauges["google"]
    assert g.value_lbl.text() == "—"
    assert g.detail_lbl.text() == "Account quota unavailable"


def test_overview_gauge_says_when_one_account_is_unavailable(qapp, monkeypatch, tmp_path):
    _history(tmp_path, [{"ts": "2026-11-19T09:05", "used": 1, "total": 2}])
    quotas = {KEY: (1, 4)}  # second account has no quota and no history

    def quota(key):
        if key in quotas:
            return quotas[key]
        raise RuntimeError("timed out")
    monkeypatch.setattr(main.cloud_quota, "quota", quota)
    monkeypatch.setattr(main, "_append_quota_sample", lambda *a, **k: None)
    ok = _tile(qapp)
    bad = main.StorageTile("GoogleDrive-other@example.com", Path.home(), True,
                           provider_override="google", display_account="other@example.com")
    page = _gauge_page([ok, bad])
    page.refresh_gauges()
    assert "1 unavailable" in page.gauges["google"].detail_lbl.text()


def test_quota_only_tile_without_path(qapp, monkeypatch, tmp_path):
    _fail(monkeypatch)
    t = main.StorageTile(KEY, None, True, provider_override="google",
                         display_account="someone@example.com", quota_only=True)
    assert t.detail_lbl.text() == "Account quota unavailable" and t.pct is None
    _history(tmp_path, [{"ts": "2026-11-19T09:05", "used": 1, "total": 4}])
    t = main.StorageTile(KEY, None, True, provider_override="google",
                         display_account="someone@example.com", quota_only=True)
    assert t.pct == 25 and "as of" in t.detail_lbl.text()


def test_real_network_errors_do_not_show_local_disk(qapp, monkeypatch):
    import requests
    for exc in (requests.Timeout("Read timed out"),
                requests.ConnectionError("Max retries exceeded"),
                requests.HTTPError("503 Server Error")):
        _fail(monkeypatch, exc)
        text = _tile(qapp).detail_lbl.text()
        assert "local disk" not in text and "free of" not in text


def test_expired_token_path_is_unchanged(qapp, monkeypatch):
    _fail(monkeypatch, RuntimeError("401 Unauthorized"))
    tile = _tile(qapp)
    assert tile.detail_lbl.text() == ""
    assert not tile.reconnect_btn.isHidden()


def test_unconnected_tile_still_shows_labelled_local_disk(qapp, monkeypatch):
    monkeypatch.setattr(main.cloud_quota, "is_connected", lambda key: False)
    tile = _tile(qapp)
    assert "(local disk)" in tile.detail_lbl.text()


def test_working_quota_is_unchanged(qapp, monkeypatch):
    monkeypatch.setattr(main.cloud_quota, "quota", lambda key: (1_000, 4_000))
    monkeypatch.setattr(main, "_append_quota_sample", lambda *a, **k: None)
    tile = _tile(qapp)
    assert "(account quota)" in tile.detail_lbl.text() and tile.pct == 25


def test_last_known_quota_ignores_junk(tmp_path):
    f = tmp_path / "quota_history.json"
    assert main._last_known_quota(KEY) is None
    f.write_text("not json")
    assert main._last_known_quota(KEY) is None
    _history(tmp_path, [{"ts": "2026-11-19T09:05", "used": 5, "total": 0}])
    assert main._last_known_quota(KEY) is None  # total 0 is no usable sample
    _history(tmp_path, [{"ts": "x", "used": 1, "total": 2},
                        {"ts": "2026-11-19T09:05", "used": 5, "total": 10}])
    assert main._last_known_quota(KEY) == (5, 10, "2026-11-19T09:05")
    for bad in ('{"%s": [{"ts": "x", "used": 1, "total": Infinity}]}' % KEY,
                '[1, 2]', '{"%s": 7}' % KEY):
        f.write_text(bad)
        assert main._last_known_quota(KEY) is None


def test_format_as_of():
    now = datetime(2026, 11, 20, 13, 30)
    assert main._format_as_of("2026-11-20T13:17", now) == "13:17"
    assert main._format_as_of("2026-11-19T09:05", now) == "19 Nov 09:05"
    assert main._format_as_of("garbage", now) == "earlier"
