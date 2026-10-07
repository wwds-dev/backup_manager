"""Scrolling the page must not stall when the pointer crosses an inner box.

The page used to hand every wheel event to whatever list, table or log was
under the pointer, so a page scroll stopped dead each time one slid beneath
the cursor. `SmartScrollArea` now latches each gesture to one target: an inner
box only when the gesture starts over it and it can move that way, the page
otherwise. Driven with real QWheelEvents through the app's event filter.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QLabel, QListWidget, QTableWidget, QTextEdit, QVBoxLayout, QWidget,
)

import main  # noqa: E402

DOWN = -120  # one wheel notch towards the end of the content


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(qapp):
    area = main.SmartScrollArea()
    area.setWidgetResizable(True)
    content = QWidget()
    lay = QVBoxLayout(content)
    above = QLabel("above")
    above.setFixedHeight(600)
    log = QTextEdit()
    log.setPlainText("\n".join(f"line {i}" for i in range(400)))
    log.setFixedHeight(140)
    below = QLabel("below")
    below.setFixedHeight(1200)
    for w in (above, log, below):
        lay.addWidget(w)
    area.setWidget(content)
    area.resize(600, 500)
    area.show()
    qapp.processEvents()
    yield area, above, log
    area.close()
    qapp.removeEventFilter(area)
    area.deleteLater()
    qapp.processEvents()


def wheel(target, dy, phase=Qt.NoScrollPhase):
    ev = QWheelEvent(QPointF(5, 5), QPointF(target.mapToGlobal(QPoint(5, 5))),
                     QPoint(0, 0), QPoint(0, dy), Qt.NoButton, Qt.NoModifier, phase, False)
    QApplication.sendEvent(target, ev)


def new_gesture(area):
    area._last_ms = None


def test_a_page_scroll_keeps_going_when_the_log_passes_under_the_pointer(page):
    area, above, log = page
    page_bar, log_bar = area.verticalScrollBar(), log.verticalScrollBar()

    wheel(above, 0, Qt.ScrollBegin)
    wheel(above, DOWN, Qt.ScrollUpdate)
    moved = page_bar.value()
    wheel(log.viewport(), DOWN, Qt.ScrollUpdate)   # pointer now over the log
    wheel(log.viewport(), DOWN, Qt.ScrollMomentum)

    assert moved > 0
    assert page_bar.value() > moved
    assert log_bar.value() == 0


def test_a_gesture_that_starts_over_the_log_scrolls_the_log(page):
    area, _, log = page

    wheel(log.viewport(), 0, Qt.ScrollBegin)
    wheel(log.viewport(), DOWN, Qt.ScrollUpdate)

    assert log.verticalScrollBar().value() > 0
    assert area.verticalScrollBar().value() == 0


def test_a_log_already_at_its_end_lets_the_page_scroll(page):
    area, _, log = page
    log.verticalScrollBar().setValue(log.verticalScrollBar().maximum())

    wheel(log.viewport(), DOWN)

    assert area.verticalScrollBar().value() > 0


def test_mouse_wheel_clicks_far_apart_start_a_new_gesture(page):
    area, above, log = page

    wheel(above, DOWN)              # page gesture
    new_gesture(area)               # ...a pause longer than GESTURE_GAP_MS
    wheel(log.viewport(), DOWN)     # fresh gesture over the log

    assert log.verticalScrollBar().value() > 0


def test_lists_and_tables_are_sized_to_show_every_row(qapp):
    lst = QListWidget()
    lst.addItems([f"folder {i}" for i in range(12)])
    table = QTableWidget(15, 3)                       # as the Lab Health table:
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)
    try:
        for view in (lst, table):
            view.resize(800, 100)                     # a card's width, not a bare widget's
            main.fit_height_to_rows(view)
            view.show()
            qapp.processEvents()
            assert view.verticalScrollBar().maximum() == 0, type(view).__name__
    finally:
        for view in (lst, table):
            view.close()
            view.deleteLater()
        qapp.processEvents()
