"""Offscreen MainWindow: every page, the theme toggle, the Overview wiring and
the P3 fixes from docs/audit/sidebar-redesign-review.md.

Nothing here may start a real backup, touch the network or read the owner's
real state: every trigger that could is patched before the window exists.
"""

from __future__ import annotations

import os
import re
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

import main  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(main, "run_cmd", lambda *a, **k: (1, "", "patched"))
    monkeypatch.setattr(main, "launchd_loaded", lambda: False)
    monkeypatch.setattr(main, "icloud_local_bytes", lambda: None)
    monkeypatch.setattr(main.cloud_quota, "load_manual_accounts", lambda: [])
    monkeypatch.setattr(main.cloud_quota, "SECRETS_DIR", tmp_path / "secrets")
    monkeypatch.setattr(main, "_set_dock_icon_visible", lambda v: False)
    monkeypatch.setattr(main.OverviewProbe, "run", lambda self: None)
    # Anything that could start a real backup is recorded instead.
    for name in ("run_backup", "run_dry_run", "run_delete_preview", "run_single_folder",
                 "_maybe_auto_backup", "_backup_on_network_up", "_backup_on_usb_mount"):
        monkeypatch.setattr(main.BackupStatusCard, name,
                            lambda self, *a, _n=name, **k: started.append(_n))
    saved_dark = main._DARK
    w = main.MainWindow()
    w.started = started
    w.show()
    qapp.processEvents()
    yield w
    main._DARK = saved_dark
    w.hide()
    w.deleteLater()
    # Let every worker the window started finish, or the interpreter aborts at
    # exit with "QThread: Destroyed while thread is still running".
    end = time.time() + 20
    while main._thread_keeper.threads and time.time() < end:
        qapp.processEvents()
        time.sleep(0.02)
    qapp.processEvents()


# -- window shell -------------------------------------------------------------
def test_every_sidebar_page_opens_and_titles_the_top_bar(win):
    for key, label, title in main.PAGES:
        win.show_page(key)
        assert win.current_page() == key
        assert win.nav[key].isChecked()
        assert win.page_title.text() == title
    assert win.started == []  # clicking around never starts a backup


def test_toggle_theme_restyles_and_flips_the_button(win):
    before = main._DARK
    win._toggle_theme()
    assert main._DARK is (not before)
    assert win._theme_btn.text() == ("☀" if main._DARK else "🌙")
    win._toggle_theme()
    assert main._DARK is before


# -- Overview wiring ----------------------------------------------------------
def test_storage_updated_refreshes_the_gauges(win):
    win.storage_card.tiles = [FakeTile("dropbox", 42, "1 GB free", "d@x")]
    win.storage_card.updated.emit()
    assert win.overview.gauges["dropbox"].value_lbl.text() == "42 %"


def test_real_wiring_lab_scan_and_time_machine_reach_the_page(win):
    win.health_card.scanned.emit([
        {"name": "proj", "has_git": True, "uncommitted": 3, "external": False, "items": []}])
    assert any("uncommitted" in lbl.text() for lbl in win.overview.findChildren(QLabel))
    win.tm_card.state = {"configured": True, "latest": "2000-01-01 00:00"}
    win.tm_card.updated.emit()
    assert win.overview.jobs["tm"].pill.text() == "Behind"


def test_runs_changed_marks_the_drive_job_running(win):
    win.overview._probe = {"info": "Last run: x — OK", "age": 1, "loaded": True,
                           "autosync": {"hourly": False, "scheduled": True, "status": "ok",
                                        "last_success": None}}
    win.backup_card.proc = object()
    win.backup_card._dry_run = False
    win.backup_card.runs_changed.emit()
    assert win.overview.backup_btn.text() == "Backing up…"
    win.backup_card.proc = None
    win.backup_card.runs_changed.emit()
    assert win.overview.backup_btn.text() == "Back up now"


# -- P3 fixes -----------------------------------------------------------------
@pytest.mark.parametrize("hours, text", [
    (0.5, "just now"), (5, "5 h ago"), (35.9, "35 h ago"), (36, "1 day ago"),
    (47, "1 day ago"), (48, "2 days ago"), (24 * 9, "9 days ago"),
])
def test_describe_age_wording(hours, text):
    assert main.describe_age(hours) == text


def test_tm_job_unparseable_backup_name_is_not_no_backup():
    job = main.tm_job({"configured": True, "latest": "Latest"})
    assert job["pill"] != "No backup"
    assert "Latest" in job["detail"]
    assert main.tm_job({"configured": True, "latest": "none found"})["pill"] == "No backup"
    assert main.tm_job({"configured": True,
                        "latest": "unknown — backup disk not connected"})["pill"] == "Disk away"


class FakeTile:
    def __init__(self, provider, pct, detail, account=""):
        self.provider = provider
        self.pct = pct
        self.account_key = account
        self.detail_lbl = QLabel(detail)
        self.account_lbl = QLabel(account)


def test_gauge_shows_the_fullest_account_and_names_it(win):
    win.storage_card.tiles = [
        FakeTile("google", 20, "80 GB free", "alice@x"),
        FakeTile("google", 85, "2 GB free", "bob@x"),
    ]
    win.overview.refresh_gauges()
    g = win.overview.gauges["google"]
    assert g.value_lbl.text() == "85 %"
    assert "bob@x" in g.detail_lbl.text()


def test_icloud_gauge_keeps_last_value_while_du_reruns(win):
    ic = main.ICloudTile.__new__(main.ICloudTile)  # no widget init: only pct/detail are read
    main.QFrame.__init__(ic)
    ic.pct, ic.detail_lbl = 12, QLabel("3 GB local cache")
    win.storage_card.tiles = [ic]
    win.overview.refresh_gauges()
    assert win.overview.gauges["icloud"].value_lbl.text() == "12 %"
    fresh = main.ICloudTile.__new__(main.ICloudTile)
    main.QFrame.__init__(fresh)
    fresh.pct, fresh.detail_lbl = None, QLabel("Calculating…")
    win.storage_card.tiles = [fresh]
    win.overview.refresh_gauges()
    g = win.overview.gauges["icloud"]
    assert g.value_lbl.text() == "12 %" and "3 GB" in g.detail_lbl.text()


def test_attention_rows_are_only_rebuilt_when_the_items_change(win):
    ov = win.overview
    drive = {"level": "ok", "pill": "Up to date"}
    tm = {"level": "warn", "pill": "Behind"}
    ov._show_attention(drive, tm, None)
    first = [ov.attention_box.itemAt(i).widget() for i in range(ov.attention_box.count())]
    ov._show_attention(drive, tm, None)
    again = [ov.attention_box.itemAt(i).widget() for i in range(ov.attention_box.count())]
    assert first and first == again
    ov._show_attention(drive, {"level": "ok", "pill": "Up to date"}, None)
    changed = [ov.attention_box.itemAt(i).widget() for i in range(ov.attention_box.count())]
    assert changed != first


def test_open_autosync_does_not_block_on_run_cmd(win, monkeypatch):
    calls = []
    monkeypatch.setattr(main.QProcess, "startDetached",
                        staticmethod(lambda prog, args: calls.append((prog, args)) or True))
    monkeypatch.setattr(main, "run_cmd",
                        lambda *a, **k: pytest.fail("run_cmd would block the GUI"))
    win.overview._open_autosync()
    assert calls == [("open", ["-a", main.AUTOSYNC_APP])]


def test_one_shared_wheel_filter_regardless_of_page_count(win):
    routers = [c for c in QApplication.instance().children() if isinstance(c, main._WheelRouter)]
    assert len(routers) == 1
    # and it still routes: a wheel event over a page reaches its SmartScrollArea
    area = win.stack.currentWidget()
    assert isinstance(area, main.SmartScrollArea)
    got = []
    area._route = lambda obj, ev: got.append(obj)
    ev = QWheelEvent(QPointF(5, 5), QPointF(area.viewport().mapToGlobal(QPoint(5, 5))),
                     QPoint(0, 0), QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
                     Qt.NoScrollPhase, False)
    QApplication.sendEvent(area.viewport(), ev)
    assert got


def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("dark", [False, True])
def test_muted_text_is_readable_on_its_backgrounds(dark):
    css = main.build_app_style(dark)
    for sel in ("#Muted", "#SidebarVersion"):
        colour = re.search(sel + r" \{\s*color: (#[0-9A-Fa-f]{6})", css).group(1)
        for bg in re.findall(r"background: (#[0-9A-Fa-f]{6})", css)[:0] or (
                ("#1C1C1E", "#2C2C2E", "#232325") if dark else ("#F2F2F7", "#FFFFFF", "#EBEBF0")):
            assert _ratio(colour, bg) >= 4.5, (sel, colour, bg)
