"""Provider registry (spec more-storage-providers, step 2): one table in cloud_quota drives
mount detection, connect/quota dispatch, Add Account and the Cloud Accounts credential form."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

import cloud_quota  # noqa: E402
import main  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(cloud_quota, "SECRETS_DIR", tmp_path)
    monkeypatch.setattr(cloud_quota, "CREDENTIALS_FILE", tmp_path / "app_credentials.json")
    monkeypatch.setattr(cloud_quota, "TOKENS_FILE", tmp_path / "tokens.json")
    monkeypatch.setattr(cloud_quota, "MANUAL_ACCOUNTS_FILE", tmp_path / "manual_accounts.json")


def test_registry_has_existing_providers():
    assert cloud_quota.PROVIDERS["google"].label == "Google Drive"
    assert cloud_quota.PROVIDERS["dropbox"].label == "Dropbox"


@pytest.mark.parametrize("name,expected", [
    ("GoogleDrive-a@b.com", "google"),
    ("googledrive-a@b.com", "google"),
    ("Dropbox", "dropbox"),
    ("Dropbox (Personal)", "dropbox"),
    ("SomethingElse", None),
    ("iCloud Drive", None),
])
def test_provider_for_name(name, expected):
    assert cloud_quota.provider_for_name(name) == expected


def test_connect_dispatches_late_bound(monkeypatch):
    calls = []
    monkeypatch.setattr(cloud_quota, "google_connect", lambda k: calls.append(("g", k)) or (True, None))
    monkeypatch.setattr(cloud_quota, "dropbox_connect", lambda k: calls.append(("d", k)) or (True, None))
    assert cloud_quota.connect("google", "k1") == (True, None)
    assert cloud_quota.connect("dropbox", "k2") == (True, None)
    assert calls == [("g", "k1"), ("d", "k2")]
    ok, err = cloud_quota.connect("nope", "k3")
    assert not ok and "Unknown provider" in err


def test_quota_dispatches_by_token_provider(monkeypatch):
    monkeypatch.setattr(cloud_quota, "load_tokens", lambda: {
        "g": {"provider": "google"}, "d": {"provider": "dropbox"}, "x": {"provider": "zzz"}})
    monkeypatch.setattr(cloud_quota, "google_quota", lambda k: (1, 2))
    monkeypatch.setattr(cloud_quota, "dropbox_quota", lambda k: (3, 4))
    assert cloud_quota.quota("g") == (1, 2)
    assert cloud_quota.quota("d") == (3, 4)
    assert cloud_quota.quota("x") is None
    assert cloud_quota.quota("missing") is None


def test_account_email_only_where_provider_has_one(monkeypatch):
    monkeypatch.setattr(cloud_quota, "dropbox_account_email", lambda k: "x@y.z")
    assert cloud_quota.account_email("dropbox", "k") == "x@y.z"
    assert cloud_quota.account_email("google", "k") is None


def test_add_account_combo_lists_quota_providers(qapp):
    dlg = main.AddAccountDialog()
    keys = [dlg.provider_combo.itemData(i) for i in range(dlg.provider_combo.count())]
    labels = [dlg.provider_combo.itemText(i) for i in range(dlg.provider_combo.count())]
    assert keys[:2] == ["google", "dropbox"]
    assert labels[:2] == ["Google Drive", "Dropbox"]
    # Quota providers first; link-only ones (step 4: Proton) after them and labelled as such.
    n_quota = len(cloud_quota.quota_providers())
    for k in keys[:n_quota]:
        assert cloud_quota.PROVIDERS[k].has_quota
    for k, label in zip(keys[n_quota:], labels[n_quota:]):
        assert not cloud_quota.PROVIDERS[k].has_quota and "link only" in label
    assert "icloud" not in keys  # iCloud has its own tile


def test_credentials_form_round_trip_and_keeps_other_keys(qapp):
    cloud_quota.save_app_credentials({"google": {"client_id": "gid", "client_secret": "gs"},
                                      "dropbox": {"app_key": "dk", "app_secret": "ds"},
                                      "future": {"x": 1}})
    dlg = main.CloudAccountsDialog()
    fields = dlg.cred_edits
    assert fields[("google", "client_id")].text() == "gid"
    assert fields[("dropbox", "app_secret")].text() == "ds"
    assert fields[("google", "client_secret")].echoMode() == QLineEdit.Password
    assert fields[("google", "client_id")].echoMode() == QLineEdit.Normal
    fields[("dropbox", "app_key")].setText("  new  ")
    dlg.save_credentials()
    saved = cloud_quota.load_app_credentials()
    assert saved["dropbox"] == {"app_key": "new", "app_secret": "ds"}
    assert saved["google"] == {"client_id": "gid", "client_secret": "gs"}
    assert saved["future"] == {"x": 1}


def test_tile_label_from_registry(qapp, monkeypatch):
    monkeypatch.setattr(cloud_quota, "is_connected", lambda k: False)
    tile = main.StorageTile("dropbox:me", None, True, provider_override="dropbox",
                            display_account="me", quota_only=True)
    names = [w.text() for w in tile.findChildren(main.QLabel) if w.objectName() == "TileName"]
    assert names == ["Dropbox"]
