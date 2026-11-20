"""Proton link-only tile and one quick-access link per tile (spec more-storage-providers, step 4).

Mounted: Open in Finder. Not mounted: the provider's registry URL (Google with authuser=<email>).
No URL ever comes from outside the registry. Proton shows no number, no bar and no gauge.
"""

from __future__ import annotations

import os
import urllib.parse
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

import cloud_quota  # noqa: E402
import main  # noqa: E402

PROTON = "ProtonDrive-someone@proton.me-folder"


@pytest.fixture(scope="session")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(cloud_quota, "SECRETS_DIR", tmp_path)
    monkeypatch.setattr(cloud_quota, "CREDENTIALS_FILE", tmp_path / "app_credentials.json")
    monkeypatch.setattr(cloud_quota, "TOKENS_FILE", tmp_path / "tokens.json")
    monkeypatch.setattr(cloud_quota, "MANUAL_ACCOUNTS_FILE", tmp_path / "manual_accounts.json")
    monkeypatch.setattr(main, "_QUOTA_HISTORY_FILE", tmp_path / "quota_history.json")
    opened = []
    monkeypatch.setattr(main, "run_cmd", lambda cmd, *a, **k: opened.append(cmd) or (0, "", ""))

    def no_quota(key):
        raise AssertionError("quota must not be called")
    monkeypatch.setattr(main.cloud_quota, "quota", no_quota)
    return opened


def _buttons(tile):
    return [b for b in tile.findChildren(QPushButton) if not b.isHidden() or b.text().startswith("Open")]


def _open_buttons(tile):
    return [b for b in tile.findChildren(QPushButton) if b.text().startswith("Open")]


def _click_open(tile, opened):
    btns = _open_buttons(tile)
    assert len(btns) == 1, [b.text() for b in btns]
    btns[0].click()
    return opened[-1]


# ---------------------------------------------------------------------------- registry
def test_proton_and_icloud_in_registry_without_quota():
    for key in ("proton", "icloud"):
        p = cloud_quota.PROVIDERS[key]
        assert not p.has_quota and p.web_url.startswith("https://")
    assert cloud_quota.provider_for_name(PROTON) == "proton"
    assert "proton" not in [p.key for p in cloud_quota.quota_providers()]


def test_every_registry_url_is_https_literal():
    for p in cloud_quota.PROVIDERS.values():
        parsed = urllib.parse.urlparse(p.web_url)
        assert parsed.scheme == "https" and parsed.netloc and not parsed.query


@pytest.mark.parametrize("account,expected", [
    ("someone@example.com", "https://drive.google.com/?authuser=someone%40example.com"),
    ("a+b@x.org", "https://drive.google.com/?authuser=a%2Bb%40x.org"),
    ("evil@x.com&next=https://bad", None),  # not a plain email: no authuser
    ("Work account", None),
    ("", None),
    (None, None),
])
def test_google_link_authuser(account, expected):
    url = cloud_quota.web_link("google", account)
    assert url == (expected or cloud_quota.PROVIDERS["google"].web_url)


def test_other_providers_ignore_account():
    for key in ("dropbox", "onedrive", "proton", "icloud"):
        assert cloud_quota.web_link(key, "someone@example.com") == cloud_quota.PROVIDERS[key].web_url


def test_unknown_provider_has_no_link():
    assert cloud_quota.web_link("nope", "x") is None


# ---------------------------------------------------------------------------- Proton tile
def test_proton_tile_shows_no_number_no_bar(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "disk_usage_for", lambda p: (_ for _ in ()).throw(AssertionError("disk")))
    tile = main.StorageTile(PROTON, tmp_path, True)
    assert tile.provider == "proton"
    assert tile.detail_lbl.text() == "No quota available (no quota API this app can use)"
    assert tile.bar.isHidden()
    assert tile.pct is None
    assert not any(ch.isdigit() for ch in tile.detail_lbl.text())
    texts = [b.text() for b in tile.findChildren(QPushButton)]
    assert not any("Connect" in t for t in texts)


def test_proton_mount_is_a_storage_target(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "cloud_services", lambda: [(PROTON, tmp_path, True)])
    names = [n for n, _p, _e in main.storage_targets()]
    assert PROTON in names


def test_proton_not_offered_for_connect_in_cloud_accounts(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "cloud_services", lambda: [(PROTON, tmp_path, True)])
    dlg = main.CloudAccountsDialog()
    texts = [w.text() for w in dlg.findChildren(QLabel)] + [b.text() for b in dlg.findChildren(QPushButton)]
    assert not any(PROTON in t for t in texts)


def test_proton_never_gets_a_gauge(qapp, tmp_path):
    tile = main.StorageTile(PROTON, tmp_path, True)
    window = SimpleNamespace(
        backup_card=SimpleNamespace(proc=None, _dry_run=False),
        tm_card=SimpleNamespace(state={"configured": None}),
        storage_card=SimpleNamespace(tiles=[tile]),
    )
    page = main.OverviewPage(window)
    page.refresh_gauges()
    assert "proton" not in page.gauges
    for g in page.gauges.values():
        assert "Proton" not in g.detail_lbl.text()


def test_proton_added_by_hand_without_oauth(qapp, monkeypatch):
    def no_connect(*a):
        raise AssertionError("no OAuth for Proton")
    monkeypatch.setattr(main, "ConnectWorker", no_connect)
    dlg = main.AddAccountDialog()
    idx = dlg.provider_combo.findData("proton")
    assert idx >= 0
    dlg.provider_combo.setCurrentIndex(idx)
    dlg.label_edit.setText("me@proton.me")
    dlg.do_connect()
    assert {"key": "proton:me@proton.me", "provider": "proton", "label": "me@proton.me"} \
        in cloud_quota.load_manual_accounts()


def test_manual_proton_tile_is_link_only(qapp, isolated):
    tile = main.StorageTile("proton:me", None, True, provider_override="proton",
                            display_account="me", quota_only=True)
    assert tile.detail_lbl.text().startswith("No quota available")
    assert tile.bar.isHidden()
    assert _click_open(tile, isolated) == ["open", "https://drive.proton.me/"]


# ---------------------------------------------------------------------------- links
def test_mounted_tile_opens_finder(qapp, isolated, monkeypatch, tmp_path):
    monkeypatch.setattr(main.cloud_quota, "is_connected", lambda k: False)
    tile = main.StorageTile("Dropbox", tmp_path, True)
    assert _click_open(tile, isolated) == ["open", str(tmp_path)]


@pytest.mark.parametrize("provider,label,expected", [
    ("google", "someone@example.com", "https://drive.google.com/?authuser=someone%40example.com"),
    ("google", "Work", "https://drive.google.com/"),
    ("dropbox", "me@x.com", "https://www.dropbox.com/home"),
    ("onedrive", "me@x.com", "https://onedrive.live.com/"),
])
def test_unmounted_tile_opens_registry_url(qapp, isolated, monkeypatch, provider, label, expected):
    monkeypatch.setattr(main.cloud_quota, "is_connected", lambda k: False)
    tile = main.StorageTile(f"{provider}:{label}", None, True, provider_override=provider,
                            display_account=label, quota_only=True)
    btn = _open_buttons(tile)[0]
    if provider == "google" and "@" in label:
        assert "account" in btn.text().lower() or "browser" in btn.text().lower()
    else:
        assert "provider page" in btn.text()
    assert _click_open(tile, isolated) == ["open", expected]


def test_link_never_uses_an_api_value(qapp, isolated, monkeypatch):
    """The account line may be rewritten from an API (Dropbox email); the link stays the registry's."""
    monkeypatch.setattr(main.cloud_quota, "is_connected", lambda k: False)
    tile = main.StorageTile("google:Work", None, True, provider_override="google",
                            display_account="Work", quota_only=True)
    tile.account_lbl.setText("attacker@evil.example")
    url = _click_open(tile, isolated)[1]
    assert url == cloud_quota.PROVIDERS["google"].web_url


def test_every_tile_has_exactly_one_open_link(qapp, isolated, monkeypatch, tmp_path):
    monkeypatch.setattr(main.cloud_quota, "is_connected", lambda k: False)
    tiles = [
        main.StorageTile("GoogleDrive-a@b.com", tmp_path, True),
        main.StorageTile("OneDrive-Personal", tmp_path, True),
        main.StorageTile(PROTON, tmp_path, True),
        main.StorageTile("dropbox:x", None, True, provider_override="dropbox",
                         display_account="x", quota_only=True),
    ]
    for t in tiles:
        assert len(_open_buttons(t)) == 1


def test_icloud_tile_link(qapp, isolated, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "icloud_local_bytes", lambda: None)
    monkeypatch.setattr(main, "icloud_access_denied", lambda: False)
    monkeypatch.setattr(main, "ICLOUD_DIR", tmp_path)
    tile = main.ICloudTile()
    assert _click_open(tile, isolated) == ["open", str(tmp_path)]
    monkeypatch.setattr(main, "ICLOUD_DIR", tmp_path / "missing")
    tile2 = main.ICloudTile()
    assert _click_open(tile2, isolated) == ["open", cloud_quota.PROVIDERS["icloud"].web_url]
    for t in (tile, tile2):
        if t._worker is not None:
            t._worker.wait(5000)
    QApplication.processEvents()
