"""Replacing a scan that is still running must not abort the app.

The Folders and Lab Health cards start a background QThread on every refresh
and used to assign it straight over the previous one. If that one was still
running, its last reference went away and Qt aborted the whole process with
"QThread: Destroyed while thread is still running".
"""

from __future__ import annotations

import gc
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThread, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main  # noqa: E402


class SlowWorker(QThread):
    done = Signal(str)

    def __init__(self, label, delay):
        super().__init__()
        self.label, self.delay = label, delay

    def run(self):
        time.sleep(self.delay)
        self.done.emit(self.label)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def wait_for(qapp, cond, timeout=5.0):
    end = time.time() + timeout
    while not cond() and time.time() < end:
        qapp.processEvents()
        time.sleep(0.01)


def test_a_superseded_scan_is_kept_alive_and_its_result_dropped(qapp):
    results = []
    old = SlowWorker("old", 0.4)
    old.done.connect(results.append)
    holder = main.replace_worker(None, old)

    new = SlowWorker("new", 0.05)
    new.done.connect(results.append)
    holder = main.replace_worker(holder, new)
    del old
    gc.collect()  # the abort happened exactly here: last reference, thread still running

    assert len(main._retired_workers) == 1
    wait_for(qapp, lambda: not main._retired_workers and not holder.isRunning())
    qapp.processEvents()

    assert results == ["new"]
    assert main._retired_workers == set()


def test_a_finished_scan_is_simply_replaced(qapp):
    first = main.replace_worker(None, SlowWorker("a", 0))
    first.wait()

    second = main.replace_worker(first, SlowWorker("b", 0))
    second.wait()

    assert main._retired_workers == set()
