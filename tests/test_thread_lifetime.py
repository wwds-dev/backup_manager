"""A background QThread must never be destroyed while it is still running.

Qt aborts the whole process when that happens ("QThread: Destroyed while
thread is still running"), and the suite caught it ~2 runs in 100: a storage
tile deleted by a refresh took its iCloud scan with it, and the last Python
reference -- the bound `run` PySide holds for the call -- went on the worker
thread itself as run() returned. The webhook thread had no owner at all and
aborted every time a backup finished with a webhook configured.

Each case runs in a child interpreter, because the failure is SIGABRT: in
process it would take pytest down with it instead of failing one test.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRELUDE = """
import gc, os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, {root!r})
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication
app = QApplication([])
import main

def drain(timeout=5.0):
    end = time.time() + timeout
    while main._thread_keeper.threads and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert not main._thread_keeper.threads, "keeper never released its threads"
"""


def run_child(body: str) -> subprocess.CompletedProcess:
    code = PRELUDE.format(root=str(ROOT)) + textwrap.dedent(body) + "\nprint('CLEAN EXIT')\n"
    return subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=60, cwd=ROOT)


def assert_clean(proc):
    assert proc.returncode == 0 and "CLEAN EXIT" in proc.stdout, (
        f"child exited {proc.returncode}\n--- stdout\n{proc.stdout}\n--- stderr\n{proc.stderr}")


def test_an_unowned_thread_survives_its_own_run():
    """Every outside reference dropped while run() is still going."""
    assert_clean(run_child("""
        class Slow(QThread):
            def run(self):
                time.sleep(0.3)

        main.start_thread(Slow())
        gc.collect()
        drain()
    """))


def test_a_tile_deleted_mid_scan_does_not_take_its_worker_with_it():
    """StorageCard.refresh() deletes the iCloud tile while its du is running."""
    assert_clean(run_child("""
        main.icloud_local_bytes = lambda: (time.sleep(0.3), 1024)[1]
        tile = main.ICloudTile()
        assert tile._worker.isRunning()
        tile.deleteLater()
        app.processEvents()
        del tile
        gc.collect()
        drain()
    """))


def test_the_webhook_thread_outlives_the_call_that_fires_it():
    """_fire_webhook used to start a thread and drop the only reference."""
    assert_clean(run_child("""
        main._load_state = lambda: {"webhook_url": "http://127.0.0.1:9/hook"}
        main.urllib.request.urlopen = lambda *a, **k: time.sleep(0.3)
        main.BackupStatusCard._fire_webhook(None, "done")
        gc.collect()
        drain()
    """))


def test_threads_are_released_on_the_gui_thread():
    """Dropping a finished thread on the worker would be the same abort, later."""
    assert_clean(run_child("""
        import threading
        seen = []

        class Spy(main._ThreadKeeper):
            def _release(self, key):
                seen.append(threading.current_thread() is threading.main_thread())
                super()._release(key)

        main._thread_keeper = Spy()
        main.start_thread = main._thread_keeper.start

        class Quick(QThread):
            def run(self):
                time.sleep(0.05)

        for _ in range(5):
            main.start_thread(Quick())
        drain()
        assert seen == [True] * 5, seen
    """))
