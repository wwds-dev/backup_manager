"""Workspace dialog: nothing pre-ticked, kept backups show why, settings are clamped."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLabel, QPushButton, QWidget  # noqa: E402

import main  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_dialog_ticks_nothing_and_lists_reasons(qapp, monkeypatch):
    class Host(QWidget):
        _workspace_ready = main.LabHealthCard._workspace_ready

    seen = {}
    monkeypatch.setattr(QDialog, "exec", lambda self: seen.update(
        boxes=self.findChildren(QCheckBox), labels=[l.text() for l in self.findChildren(QLabel)]) or 0)
    h = Host()
    h.workspace_btn = QPushButton()
    h._workspace_ready({
        "backups": [
            {"path": Path("/x/backups/a"), "rel": "backups/a", "kb": 1024, "days": 50, "refs": [],
             "reasons": [], "eligible": True},
            {"path": Path("/x/backups/b"), "rel": "backups/b", "kb": 1024, "days": 50,
             "refs": ["AGENTS.md"], "reasons": ["named in AGENTS.md"], "eligible": False}],
        "caches": [{"path": Path("/x/__pycache__"), "rel": "__pycache__", "kb": 4}],
        "archive": [{"path": Path("/x/archive/o"), "rel": "archive/o", "kb": 5, "days": 9,
                     "git_members": [{"rel": "archive/o/r", "offered": False, "reasons": ["dirty"]}]}]})
    boxes = seen["boxes"]
    assert len(boxes) == 3 and not any(b.isChecked() for b in boxes if b.text() != "Weekly report-only scan")
    assert any("kept: named in AGENTS.md" in t for t in seen["labels"])
    assert any("archive/o/r: kept (dirty)" in t for t in seen["labels"])


def test_settings_clamped(monkeypatch):
    monkeypatch.setattr(main, "_load_state", lambda: {"worktree_min_days": 1, "backup_min_days": "x",
                                                      "workspace_weekly_scan": False})
    cfg = main.workspace_settings()
    assert cfg == {"worktree_days": 7, "backup_days": 30, "weekly": False}
