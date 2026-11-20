"""Google tile: Drive files vs "Photos, Gmail and other" split (spec more-storage-providers, step 1).

The split is a difference (`usage - usageInDrive`), never a Photos number: the label never says
"Photos" alone, trash is shown separately and never subtracted, and an invalid split shows nothing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import cloud_quota  # noqa: E402
import main  # noqa: E402

KEY = "GoogleDrive-someone@example.com"
GB = 1_000_000_000


# ---------------------------------------------------------------------------- Qt-free rule
def test_split_valid():
    assert cloud_quota.drive_split(50 * GB, 20 * GB, 1 * GB) == (20 * GB, 30 * GB, 1 * GB)


def test_split_trash_is_passed_through_not_subtracted():
    drive, other, trash = cloud_quota.drive_split(50 * GB, 20 * GB, 5 * GB)
    assert other == 30 * GB  # not 25
    assert trash == 5 * GB


def test_split_drive_equal_to_used_is_valid():
    assert cloud_quota.drive_split(10, 10, None) == (10, 0, None)


def test_split_zero_drive_is_valid():
    assert cloud_quota.drive_split(10, 0, None) == (0, 10, None)


def test_split_missing_drive_gives_nothing():
    assert cloud_quota.drive_split(10, None, 3) == (None, None, 3)


def test_split_negative_difference_gives_nothing():
    assert cloud_quota.drive_split(10, 11, None) == (None, None, None)


def test_split_negative_drive_gives_nothing():
    assert cloud_quota.drive_split(10, -1, None) == (None, None, None)


# ---------------------------------------------------------------------------- Quota tuple
def test_quota_unpacks_as_pair_and_compares_as_tuple():
    q = cloud_quota.Quota(5, 10, drive=2, trash=1)
    used, total = q
    assert (used, total) == (5, 10)
    assert q == (5, 10)
    assert q.drive == 2 and q.trash == 1


def test_quota_defaults_have_no_split():
    q = cloud_quota.Quota(5, None)
    assert q.drive is None and q.trash is None
    assert len(q) == 2


class _Resp:
    def __init__(self, data):
        self._data = data
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def _google(monkeypatch, quota_fields):
    monkeypatch.setattr(cloud_quota, "load_tokens",
                        lambda: {KEY: {"provider": "google", "refresh_token": "r"}})
    monkeypatch.setattr(cloud_quota, "_google_access_token", lambda rt: "a")
    monkeypatch.setattr(cloud_quota.requests, "get",
                        lambda *a, **k: _Resp({"storageQuota": quota_fields}))
    return cloud_quota.google_quota(KEY)


def test_google_quota_reads_drive_and_trash(monkeypatch):
    q = _google(monkeypatch, {"limit": "100", "usage": "50", "usageInDrive": "20",
                              "usageInDriveTrash": "3"})
    assert q == (50, 100)
    assert q.drive == 20 and q.trash == 3


def test_google_quota_without_drive_fields(monkeypatch):
    q = _google(monkeypatch, {"limit": "100", "usage": "50"})
    assert q == (50, 100)
    assert q.drive is None and q.trash is None


# ---------------------------------------------------------------------------- history
@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(main.cloud_quota, "SECRETS_DIR", tmp_path)
    monkeypatch.setattr(main, "_QUOTA_HISTORY_FILE", tmp_path / "quota_history.json")


def test_history_keeps_split_and_old_samples_still_read(tmp_path):
    (tmp_path / "quota_history.json").write_text(json.dumps(
        {KEY: [{"ts": "2026-11-19T09:05", "used": 1, "total": 10}]}))
    assert main._last_known_split(KEY) is None  # old sample: no split keys, still valid
    assert main._last_known_quota(KEY) == (1, 10, "2026-11-19T09:05")
    main._append_quota_sample(KEY, 5, 10, drive=2, trash=1)
    assert main._last_known_split(KEY) == (2, 1)
    sample = main._get_quota_history(KEY)[-1]
    assert sample["drive"] == 2 and sample["trash"] == 1


def test_history_without_split_writes_no_keys():
    main._append_quota_sample(KEY, 5, 10)
    sample = main._get_quota_history(KEY)[-1]
    assert "drive" not in sample and "trash" not in sample


def test_last_known_split_follows_the_same_sample_as_last_known_quota(tmp_path):
    # newest sample unusable (total 0): both readers fall back to the older one
    (tmp_path / "quota_history.json").write_text(json.dumps({KEY: [
        {"ts": "2026-11-18T08:00", "used": 5, "total": 10, "drive": 2, "trash": 1},
        {"ts": "2026-11-19T08:00", "used": 5, "total": 0, "drive": 4},
    ]}))
    assert main._last_known_quota(KEY)[2] == "2026-11-18T08:00"
    assert main._last_known_split(KEY) == (2, 1)


# ---------------------------------------------------------------------------- tile
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(main.build_app_style(False))
    yield app


def _tile(qapp, monkeypatch, result=None, error=None):
    monkeypatch.setattr(main.cloud_quota, "is_connected", lambda key: True)
    monkeypatch.setattr(main.cloud_quota, "dropbox_account_email", lambda key: None)

    def fake(key):
        if error:
            raise RuntimeError(error)
        return result
    monkeypatch.setattr(main.cloud_quota, "quota", fake)
    tile = main.StorageTile(KEY, Path.home(), True, provider_override="google",
                            display_account="someone@example.com")
    w = tile._quota_worker
    if w is not None:
        assert w.wait(5000)
    QApplication.processEvents()
    return tile


def _split_text(tile):
    return "\n".join(l.text() for l in tile.split_lbls if not l.isHidden())


def test_tile_shows_two_lines(qapp, monkeypatch):
    tile = _tile(qapp, monkeypatch, cloud_quota.Quota(50 * GB, 100 * GB, drive=20 * GB, trash=1 * GB))
    text = _split_text(tile)
    assert "Drive files" in text and "trash" in text
    assert "Photos, Gmail and other" in text
    assert "total minus drive files" in tile.split_lbls[1].toolTip().lower()


def test_tile_trash_hidden_when_absent(qapp, monkeypatch):
    tile = _tile(qapp, monkeypatch, cloud_quota.Quota(50 * GB, 100 * GB, drive=20 * GB))
    assert "trash" not in _split_text(tile)
    assert "Drive files" in _split_text(tile)


@pytest.mark.parametrize("result", [
    (50 * GB, 100 * GB),  # plain tuple, as older fakes return
    cloud_quota.Quota(50 * GB, 100 * GB),
    cloud_quota.Quota(50 * GB, 100 * GB, drive=60 * GB, trash=1 * GB),  # negative difference
])
def test_tile_hides_split_when_invalid(qapp, monkeypatch, result):
    tile = _tile(qapp, monkeypatch, result)
    assert _split_text(tile) == ""
    assert "used of" in tile.detail_lbl.text()


def test_photos_never_alone(qapp, monkeypatch):
    tile = _tile(qapp, monkeypatch, cloud_quota.Quota(50 * GB, 100 * GB, drive=20 * GB, trash=1 * GB))
    # Label and tooltip text alike (review P3-1): "Photos" only ever as "Photos, Gmail and other".
    for lbl in tile.split_lbls:
        for text in (lbl.text(), lbl.toolTip()):
            assert text.count("Photos") == text.count("Photos, Gmail and other"), text


def test_failed_call_shows_old_split_as_of(qapp, monkeypatch, tmp_path):
    (tmp_path / "quota_history.json").write_text(json.dumps({KEY: [
        {"ts": "2026-11-19T09:05", "used": 50 * GB, "total": 100 * GB, "drive": 20 * GB, "trash": GB}]}))
    tile = _tile(qapp, monkeypatch, error="503 Service Unavailable")
    assert "as of" in tile.detail_lbl.text()
    assert "Photos, Gmail and other" in _split_text(tile)


def test_successful_call_records_split(qapp, monkeypatch):
    _tile(qapp, monkeypatch, cloud_quota.Quota(50 * GB, 100 * GB, drive=20 * GB, trash=GB))
    assert main._last_known_split(KEY) == (20 * GB, GB)
