"""Table columns: fitted to the window until the user drags one, then remembered.

`ResizableColumns` backs both the Backed-up Folders and Lab Health tables. The
widths a user drags must survive a relaunch (state.json) and must not be undone
by the next refresh, while an untouched table keeps fitting itself.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QTableWidget  # noqa: E402

import main  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def scratch_state(tmp_path, monkeypatch):
    """Never touch the real state.json."""
    monkeypatch.setattr(main, "_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(main.cloud_quota, "SECRETS_DIR", tmp_path)


@pytest.fixture
def make_table(qapp):
    made = []

    def make():
        table = QTableWidget(3, 3)
        table.resize(600, 200)
        fits = []

        def auto_fit():
            fits.append(1)
            table.setColumnWidth(0, 300)
            table.setColumnWidth(1, 100)

        cols = main.ResizableColumns(table, "t", auto_fit)
        table.show()
        qapp.processEvents()
        made.append(table)
        return table, cols, fits

    yield make
    for table in made:
        table.close()
        table.deleteLater()
    qapp.processEvents()


def drag(monkeypatch, table, col, width):
    """Resize a column the way a mouse drag does: with the left button down."""
    monkeypatch.setattr(main.QApplication, "mouseButtons", staticmethod(lambda: Qt.LeftButton))
    table.setColumnWidth(col, width)
    monkeypatch.undo()


def test_an_untouched_table_fits_itself(make_table):
    table, cols, fits = make_table()
    cols.fit()

    assert fits
    assert table.columnWidth(0) == 300
    assert cols.user_sized is False


def test_our_own_resizing_is_not_mistaken_for_the_user(make_table):
    table, cols, _ = make_table()
    table.setColumnWidth(0, 250)  # no mouse button down

    assert cols.user_sized is False


def test_a_dragged_width_survives_the_next_refresh(make_table, monkeypatch):
    table, cols, fits = make_table()
    drag(monkeypatch, table, 0, 420)
    fits.clear()

    cols.fit()

    assert cols.user_sized is True
    assert fits == []
    assert table.columnWidth(0) == 420


def test_dragged_widths_are_restored_after_a_relaunch(make_table, monkeypatch):
    table, cols, _ = make_table()
    drag(monkeypatch, table, 0, 420)
    cols.save()  # what the debounce timer does

    table2, cols2, fits2 = make_table()
    cols2.fit()

    assert cols2.user_sized is True
    assert table2.columnWidth(0) == 420
    assert fits2 == []


def test_fit_columns_to_window_hands_control_back(make_table, monkeypatch):
    table, cols, fits = make_table()
    drag(monkeypatch, table, 0, 420)
    cols.save()
    fits.clear()

    cols.reset()

    assert cols.user_sized is False
    assert fits
    assert table.columnWidth(0) == 300
    assert "t" not in main._load_state().get(main.ResizableColumns.STATE_KEY, {})


def test_saved_widths_for_a_different_column_count_are_ignored(make_table):
    main._save_state({main.ResizableColumns.STATE_KEY: {"t": [10, 20]}})

    _, cols, _ = make_table()

    assert cols.user_sized is False
