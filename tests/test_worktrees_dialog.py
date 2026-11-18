"""The Worktrees dialog on the Lab Health card: offered rows get a box, kept rows a reason."""
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QLabel, QPushButton,  # noqa: E402
                               QWidget)

import main  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _row(name, eligible, reasons=()):
    return {"path": Path("/x") / name, "rel": name, "repo": Path("/x/r"), "branch": "b",
            "head": "h", "locked": False, "kb": 2048, "reasons": list(reasons),
            "eligible": eligible}


def test_dialog_ticks_nothing_and_shows_why_rows_are_kept(qapp, monkeypatch):
    class Host(QWidget):   # only the dialog code is under test, not the whole card
        _worktrees_ready = main.LabHealthCard._worktrees_ready

    card = Host()
    shown = {}

    def fake_exec(self):
        shown["boxes"] = self.findChildren(QCheckBox)
        shown["labels"] = [lb.text() for lb in self.findChildren(QLabel)]
        return 0

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    card.worktrees_btn = QPushButton()
    card._worktrees_ready([
        _row("offer-me", True), _row("dirty", False, ["3 uncommitted or untracked files"])])
    assert [b.isChecked() for b in shown["boxes"]] == [False]          # nothing pre-ticked
    assert len(shown["boxes"]) == 1 and "offer-me" in shown["boxes"][0].text()
    assert any("kept: 3 uncommitted" in t for t in shown["labels"])
