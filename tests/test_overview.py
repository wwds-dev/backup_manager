"""Overview page: the status rules behind the banner, job pills and gauges.

The rules are plain functions so they are tested without a window; the last
tests drive the real Gauge and the attention list through Qt.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import main  # noqa: E402

LAUNCHCTL = (
    "PID\tStatus\tLabel\n"
    "-\t0\tcom.example.git-autosync-login\n"
    "-\t0\tcom.example.git-autosync\n"
    "-\t0\tcom.example.git-autosync-hourly\n"
    "-\t0\tcom.apple.something\n"
)


def stamp(hours_ago):
    return (datetime.now() - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")


# -- storage thresholds -------------------------------------------------------
@pytest.mark.parametrize("pct, level", [
    (None, "idle"), (0, "ok"), (69, "ok"), (70, "warn"), (89, "warn"), (90, "bad"), (100, "bad"),
])
def test_usage_level_thresholds_match_the_storage_tiles(pct, level):
    assert main.usage_level(pct) == level


# -- git_autosync state files ---------------------------------------------------
def test_autosync_state_reads_status_stamps_and_schedule(tmp_path):
    (tmp_path / "last_status.txt").write_text("attention\n")
    (tmp_path / "last_success.txt").write_text("2026-11-10 21:31:25\n")
    (tmp_path / "last_sync.txt").write_text("2026-11-10 21:31:25\n")
    st = main.autosync_state(tmp_path, LAUNCHCTL)
    assert st["status"] == "attention"
    assert st["last_success"] == datetime(2026, 11, 10, 21, 31, 25)
    assert st["last_backup"] is None
    assert st["scheduled"] and st["hourly"]


def test_autosync_state_without_files_or_agents_is_unknown(tmp_path):
    st = main.autosync_state(tmp_path, "PID\tStatus\tLabel\n")
    assert st["status"] == "unknown"
    assert not st["scheduled"] and not st["hourly"]


def test_login_agent_alone_is_not_a_schedule(tmp_path):
    st = main.autosync_state(tmp_path, "-\t0\tcom.example.git-autosync-login\n")
    assert not st["scheduled"]


def test_autosync_job_pills(tmp_path):
    base = {"status": "ok", "last_success": datetime.now() - timedelta(hours=3),
            "last_sync": None, "last_backup": None, "scheduled": True, "hourly": True}
    assert main.autosync_job(base)["level"] == "ok"
    assert main.autosync_job({**base, "status": "attention"})["pill"] == "Needs attention"
    assert main.autosync_job({**base, "last_success": datetime.now() - timedelta(days=3)})["level"] == "warn"
    assert main.autosync_job({**base, "status": "unknown"})["level"] == "idle"


# -- Google Drive and Time Machine rows ---------------------------------------
def test_drive_job_levels():
    ok = "Last run: 2026-11-10 10:10:12  —  OK"
    assert main.drive_job(ok, 5, True, "03:30")["level"] == "ok"
    assert main.drive_job(ok, 30, True, "03:30")["pill"] == "Overdue"
    assert main.drive_job(ok, 30, True, "03:30")["level"] == "warn"
    assert main.drive_job(ok, 100, True, "03:30")["level"] == "bad"
    assert main.drive_job(ok, 5, False, "03:30")["pill"] == "Manual only"
    errs = "Last run: 2026-11-10 10:10:12  —  ERRORS"
    assert main.drive_job(errs, 5, True, "03:30")["pill"] == "Errors"
    assert main.drive_job("No backups run yet.", None, True, "03:30")["level"] == "bad"
    assert main.drive_job(ok, 5, True, "03:30", running=True)["level"] == "info"


def test_tm_job_levels():
    recent = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
    old = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M")
    assert main.tm_job({"configured": None})["level"] == "idle"
    assert main.tm_job({"configured": False})["pill"] == "Not set up"
    assert main.tm_job({"configured": True, "latest": recent, "running": False})["level"] == "ok"
    assert main.tm_job({"configured": True, "latest": old, "running": False})["level"] == "bad"
    away = {"configured": True, "latest": "unknown — backup disk not connected", "running": False}
    assert main.tm_job(away)["pill"] == "Disk away"
    assert main.tm_job({"configured": True, "latest": recent, "running": True})["level"] == "info"


# -- banner ---------------------------------------------------------------------
def job(level, pill="x"):
    return {"level": level, "pill": pill, "detail": ""}


def test_banner_is_green_only_when_every_job_is():
    level, headline, summary = main.protection_banner(job("ok"), job("ok"), job("ok"), 0)
    assert (level, headline) == ("ok", "Your Mac is protected")
    assert "every project committed" in summary
    assert main.protection_banner(job("ok"), job("warn"), job("ok"), 0)[0] == "warn"


def test_a_broken_drive_backup_turns_the_banner_red():
    assert main.protection_banner(job("bad"), job("ok"), job("ok"), 0)[0] == "bad"


def test_banner_counts_uncommitted_projects():
    summary = main.protection_banner(job("ok"), job("ok"), job("ok"), 2)[2]
    assert "2 projects with uncommitted work" in summary


# -- Lab Health summary ---------------------------------------------------------
def test_lab_attention_counts_dirty_repos_and_reclaimable_space():
    rows = [
        {"name": "a", "has_git": True, "uncommitted": 3, "external": False,
         "items": [{"kind": "junk", "kb": 100, "eligible": True},
                   {"kind": "env", "kb": 1000, "eligible": False}]},
        {"name": "b", "has_git": True, "uncommitted": 0, "external": False,
         "items": [{"kind": "env", "kb": 500, "eligible": True}]},
        {"name": "linked", "has_git": True, "uncommitted": 1, "external": True,
         "items": [{"kind": "junk", "kb": 9999, "eligible": True}]},
    ]
    out = main.lab_attention(rows)
    assert out["dirty"] == ["a", "linked"]
    assert out["reclaim_kb"] == 600  # locked envs and linked projects are never offered


# -- widgets --------------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(main.build_app_style(False))
    yield app


def test_gauge_shows_percent_and_colours_the_bar(qapp):
    g = main.Gauge("Mac disk")
    g.set_value(75, "200 GB free")
    assert g.value_lbl.text() == "75 %"
    assert g.bar.property("level") == "warn"
    g.set_value(None, "Not set up on this Mac")
    assert g.value_lbl.text() == "—"
    assert g.bar.property("level") == "idle"


def test_both_themes_build_a_style_sheet_with_the_new_shell():
    for dark in (False, True):
        css = main.build_app_style(dark)
        assert "#Sidebar" in css and '#Pill[level="bad"]' in css
        assert main.LEVEL_COLORS[dark]["accent"] in css


def test_every_page_has_a_sidebar_entry_and_settings_is_last():
    keys = [k for k, *_ in main.PAGES]
    assert keys[0] == "overview" and keys[-1] == "settings"
    assert {"storage", "folders", "labhealth", "timemachine", "history"} <= set(keys)
