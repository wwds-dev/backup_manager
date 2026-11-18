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


class _SyncWorker:
    """CallWorker stand-in: runs at once on the test thread."""
    def __init__(self, fn):
        self._fn, self._cb = fn, None
        self.done = self

    def connect(self, cb):
        self._cb = cb
        self._cb(self._fn())

    def isRunning(self):
        return False


def _data(tmp):
    return {"backups": [{"path": tmp / "backups" / "a", "rel": "backups/a", "kb": 1024, "days": 50,
                         "refs": [], "reasons": [], "eligible": True},
                        {"path": tmp / "backups" / "b", "rel": "backups/b", "kb": 1024, "days": 50,
                         "refs": ["AGENTS.md"], "reasons": ["named in AGENTS.md"], "eligible": False}],
            "caches": [{"path": tmp / "__pycache__", "rel": "__pycache__", "kb": 4}], "archive": []}


def _open(qapp, monkeypatch, tmp_path, answer):
    from PySide6.QtWidgets import QMessageBox
    calls = {"trash": [], "caches": [], "ages": []}

    class Host(QWidget):
        _workspace_ready = main.LabHealthCard._workspace_ready

    monkeypatch.setattr(main, "CallWorker", _SyncWorker)
    monkeypatch.setattr(main, "replace_worker", lambda old, new: new)
    monkeypatch.setattr(main, "_load_state", lambda: {})
    monkeypatch.setattr(main, "_save_state", lambda d: None)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: (
        calls.update(default=self.defaultButton().text() if self.defaultButton() else None) or answer))

    def fake_trash(item, root, mover, *, min_days, **kw):
        calls["trash"].append(item["rel"]); calls["ages"].append(min_days)
        return True, "ok"
    monkeypatch.setattr(main.workspace_extra, "trash_backup", fake_trash)
    monkeypatch.setattr(main.workspace_extra, "clean_caches",
                        lambda paths, root: calls["caches"].extend(paths) or [(p, True, "ok") for p in paths])
    seen = {}
    monkeypatch.setattr(QDialog, "exec", lambda self: seen.update(dlg=self) or 0)
    h = Host()
    h.workspace_btn = QPushButton()
    h._workspace_ready(_data(tmp_path))
    return seen["dlg"], calls


def _tickable(dlg):
    return [b for b in dlg.findChildren(QCheckBox) if b.text() != "Weekly report-only scan"]


def _clean(dlg):
    next(b for b in dlg.findChildren(QPushButton) if "Clean checked" in b.text()).click()


def test_clean_only_acts_on_ticked_items(qapp, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox
    dlg, calls = _open(qapp, monkeypatch, tmp_path, QMessageBox.Yes)
    boxes = _tickable(dlg)
    assert len(boxes) == 2                      # kept backup 'b' has no checkbox
    _clean(dlg)
    assert calls["trash"] == [] and calls["caches"] == []      # nothing ticked, nothing done
    boxes[0].setChecked(True)                   # backup a only
    _clean(dlg)
    assert calls["trash"] == ["backups/a"] and calls["caches"] == []
    assert calls["ages"] == [30]                # the age setting reaches the click-time re-check


def test_cancel_and_default_button_do_nothing_destructive(qapp, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox
    dlg, calls = _open(qapp, monkeypatch, tmp_path, QMessageBox.Cancel)
    for b in _tickable(dlg):
        b.setChecked(True)
    _clean(dlg)
    assert calls["trash"] == [] and calls["caches"] == []
    assert calls["default"] and "Cancel" in calls["default"]


def test_ticked_cache_is_cleaned_after_yes(qapp, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox
    dlg, calls = _open(qapp, monkeypatch, tmp_path, QMessageBox.Yes)
    [b for b in _tickable(dlg) if "__pycache__" in b.text()][0].setChecked(True)
    _clean(dlg)
    assert calls["caches"] == [tmp_path / "__pycache__"] and calls["trash"] == []


def _scan_host(monkeypatch, state, saved):
    class Host(QWidget):
        _maybe_weekly_scan = main.LabHealthCard._maybe_weekly_scan

    monkeypatch.setattr(main, "CallWorker", _SyncWorker)
    monkeypatch.setattr(main, "replace_worker", lambda old, new: new)
    monkeypatch.setattr(main, "_load_state", lambda: dict(state))
    monkeypatch.setattr(main, "_save_state", lambda d: saved.append(d))
    h = Host()
    h.workspace_btn = QPushButton()
    return h


def test_weekly_scan_reports_saves_time_and_deletes_nothing(qapp, monkeypatch, tmp_path):
    import shutil
    saved, reports = [], []
    monkeypatch.setattr(main, "WORKSPACE_REPORT", tmp_path / "r.json")
    monkeypatch.setattr(main.workspace_extra, "build_report", lambda *a, **k: {
        "scanned": 123.0, "offered_items": 2, "offered_kb": 2048})
    monkeypatch.setattr(main.workspace_extra, "write_report", lambda rep, p: reports.append((rep, p)))
    for name in ("trash_backup", "clean_caches"):
        monkeypatch.setattr(main.workspace_extra, name, lambda *a, **k: pytest.fail("scan must not delete"))
    monkeypatch.setattr(shutil, "rmtree", lambda *a, **k: pytest.fail("scan must not delete"))
    h = _scan_host(monkeypatch, {}, saved)
    h._maybe_weekly_scan()
    assert reports and reports[0][1] == tmp_path / "r.json"
    assert saved and saved[0]["last_workspace_scan"] == 123.0
    assert "2 item(s)" in h.workspace_btn.toolTip()


def test_weekly_scan_respects_switch_and_interval(qapp, monkeypatch):
    import time
    ran = []
    monkeypatch.setattr(main.workspace_extra, "build_report", lambda *a, **k: ran.append(1) or {"scanned": 1.0, "offered_items": 0, "offered_kb": 0})
    monkeypatch.setattr(main.workspace_extra, "write_report", lambda *a: None)
    _scan_host(monkeypatch, {"workspace_weekly_scan": False}, [])._maybe_weekly_scan()
    _scan_host(monkeypatch, {"last_workspace_scan": time.time() - 3600}, [])._maybe_weekly_scan()
    assert ran == []
    _scan_host(monkeypatch, {"last_workspace_scan": time.time() - 8 * 86400}, [])._maybe_weekly_scan()
    assert ran == [1]
