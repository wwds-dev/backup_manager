"""Storage tiles are one size, and none of their text is clipped.

The tile row is a FlowLayout. It used each tile's sizeHint(), so a tile with fewer
lines came out shorter than its neighbours, and a tile whose wrapped label needed
more height at the fixed 230px width (a long Proton account line, "No quota
available (no quota API this app can use)") was laid out too short and the last
line was cut off.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget  # noqa: E402

import cloud_quota  # noqa: E402
import main  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(main.build_app_style(False))
    yield app


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(cloud_quota, "SECRETS_DIR", tmp_path)
    monkeypatch.setattr(cloud_quota, "CREDENTIALS_FILE", tmp_path / "app_credentials.json")
    monkeypatch.setattr(cloud_quota, "TOKENS_FILE", tmp_path / "tokens.json")
    monkeypatch.setattr(cloud_quota, "MANUAL_ACCOUNTS_FILE", tmp_path / "manual_accounts.json")
    monkeypatch.setattr(main, "_QUOTA_HISTORY_FILE", tmp_path / "quota_history.json")
    monkeypatch.setattr(main, "run_cmd", lambda *a, **k: (0, "", ""))
    monkeypatch.setattr(main, "icloud_local_bytes", lambda: 16 * 1024 * 1024)
    monkeypatch.setattr(main, "disk_usage_for", lambda p: None)


def _row(qapp, tiles, width):
    host = QWidget()
    flow = main.FlowLayout(host, spacing=10)
    for t in tiles:
        flow.addWidget(t)
    host.resize(width, flow.heightForWidth(width))
    host.show()
    qapp.processEvents()
    return host, flow


def _tiles():
    short = main.StorageTile("Dropbox", None, True, provider_override="dropbox",
                             display_account="a@b.de", quota_only=True)
    proton = main.StorageTile(
        "Proton Drive sapio1337@proton.me", None, True, provider_override="proton",
        display_account="sapio1337@proton.me (21-10-2026 23:38)", quota_only=True)
    google = main.StorageTile("Google Drive x", None, True, provider_override="google",
                              display_account="someone@example.com", quota_only=True)
    google.detail_lbl.setText("41.7 GB used of 100.0 GB (account quota)")
    for lbl, txt in zip(google.split_lbls, ("Drive files 20.8 GB · trash 0.0 B",
                                            "Photos, Gmail and other 20.9 GB")):
        lbl.setText(txt)
        lbl.setVisible(True)
    return [short, proton, google, main.ICloudTile()]


@pytest.mark.parametrize("width", [1100, 520, 240])
def test_all_tiles_same_size(qapp, width):
    tiles = _tiles()
    host, _flow = _row(qapp, tiles, width)
    sizes = {(t.width(), t.height()) for t in tiles}
    assert len(sizes) == 1, sizes
    host.close()


@pytest.mark.parametrize("width", [1100, 240])
def test_no_text_is_clipped(qapp, width):
    tiles = _tiles()
    host, _flow = _row(qapp, tiles, width)
    for t in tiles:
        for lbl in t.findChildren(QLabel):
            if lbl.isHidden() or not lbl.text():
                continue
            need = lbl.heightForWidth(lbl.width()) if lbl.wordWrap() else lbl.sizeHint().height()
            assert lbl.height() >= need, (lbl.text(), lbl.height(), need)
        for b in t.findChildren(QPushButton):
            if b.isHidden():
                continue
            assert b.width() >= b.fontMetrics().horizontalAdvance(b.text()), b.text()
        content_bottom = max(c.geometry().bottom() for c in t.findChildren(QWidget)
                             if c.parent() is t and not c.isHidden())
        assert content_bottom <= t.height(), (content_bottom, t.height())
    host.close()


def test_account_date_is_always_on_its_own_line_below_the_email(qapp):
    """macOS appends " (DD-MM-YYYY HH:MM)" to a re-created account folder; it must never
    sit on the email's line, however long the email is."""
    cases = {
        "sapio1337@proton.me (21-10-2026 23:38)": "sapio1337@proton.me\n(21-10-2026 23:38)",
        "a-very-long-address.with.parts@example-provider.com (22-06-2026 22:10)":
            "a-very-long-address.with.parts@example-provider.com\n(22-06-2026 22:10)",
        "opaque1337@proton.me": "opaque1337@proton.me",
        "": "",
    }
    for raw, shown in cases.items():
        assert main.account_display(raw) == shown
    tile = main.StorageTile("Proton Drive x", None, True, provider_override="proton",
                            display_account="sapio1337@proton.me (21-10-2026 23:38)",
                            quota_only=True)
    host, _flow = _row(qapp, [tile], 400)
    first, second = tile.account_lbl.text().split("\n")
    assert first == "sapio1337@proton.me" and second == "(21-10-2026 23:38)"
    host.close()
