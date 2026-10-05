"""Storage tiles must never escape the window as free-floating panels.

Two separate ways they did. Both put a real top-level NSWindow on screen, and
both were reported as "every destination tile pops up when the app starts":

  * `StorageTile.__init__` called `setVisible(True)` on the account label before
    adding it to the tile's layout. A widget with no parent *is* a window, so
    that showed a sliver of a window for every tile that has an account line.

  * `StorageCard.refresh()` dropped the old tiles with `setParent(None)`, which
    makes a visible widget a visible top-level window — Qt does not hide it for
    you. Every refresh (the 5-minute timer, a theme change, network coming back,
    "Refresh all") popped the whole row of tiles out as 230px panels.

These are checked by behaviour, through the real widgets, because nothing about
the source of either line looks wrong on its own.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

import main  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(main.build_app_style(False))
    yield app


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """No network, and no writes to the user's real quota history."""
    monkeypatch.setattr(main.cloud_quota, "quota",
                        lambda key: (1_300_000_000, 15_000_000_000))
    monkeypatch.setattr(main.cloud_quota, "dropbox_account_email",
                        lambda key: "someone@example.com")
    monkeypatch.setattr(main.cloud_quota, "SECRETS_DIR", tmp_path)
    monkeypatch.setattr(main, "_append_quota_sample", lambda *a, **k: None)


def _stray_windows(app, expected):
    return [w for w in app.topLevelWidgets()
            if w.isVisible() and w is not expected]


def test_building_a_tile_shows_no_window(qapp):
    """A tile with an account line must not flash a window while being built."""
    shown = []
    original = QWidget.setVisible

    def setVisible(self, visible):
        if visible and self.parent() is None and self.isWindow():
            shown.append(f"{type(self).__name__}[{self.objectName()}]")
        original(self, visible)

    QWidget.setVisible = setVisible
    try:
        tile = main.StorageTile(
            "GoogleDrive-someone@example.com", None, True,
            provider_override="google", display_account="someone@example.com",
            quota_only=True,
        )
    finally:
        QWidget.setVisible = original
    assert shown == [], f"shown as top-level windows during construction: {shown}"
    assert tile.account_lbl.isVisible() is False or tile.account_lbl.parent() is tile


def test_refresh_does_not_pop_tiles_out_as_windows(qapp):
    """Refreshing a visible card must not leave the old tiles on screen."""
    host = QWidget()
    QVBoxLayout(host).addWidget(card := main.StorageCard())
    host.resize(900, 300)
    host.show()
    qapp.processEvents()
    assert _stray_windows(qapp, host) == []

    old = list(card.tiles)
    assert old, "no tiles to begin with — the test proves nothing"

    card.refresh()
    qapp.processEvents()

    floating = [f"{type(t).__name__} {t.width()}x{t.height()}"
                for t in old if t.isVisible()]
    assert floating == [], f"old tiles left on screen after refresh: {floating}"
    assert _stray_windows(qapp, host) == []
    host.close()
