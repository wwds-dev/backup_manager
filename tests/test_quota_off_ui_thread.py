"""Cloud quota is fetched off the GUI thread (audit H2), and a late result is never misapplied.

`StorageTile.set_usage` used to call `cloud_quota.quota()` / `dropbox_account_email()` on the
GUI thread (20 s timeouts, per account, on every Storage refresh). Now a worker does it;
the tile renders at once from the last known sample. Spec: docs/specs/quota-off-ui-thread.md.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

import main  # noqa: E402

KEY = "GoogleDrive-someone@example.com"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(main.build_app_style(False))
    yield app


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(main.cloud_quota, "SECRETS_DIR", tmp_path)
    monkeypatch.setattr(main, "_QUOTA_HISTORY_FILE", tmp_path / "quota_history.json")
    monkeypatch.setattr(main.cloud_quota, "is_connected", lambda key: True)
    monkeypatch.setattr(main.cloud_quota, "dropbox_account_email", lambda key: None)


def _history(tmp_path, samples):
    (tmp_path / "quota_history.json").write_text(json.dumps({KEY: samples}))


def _tile(provider="google", key=KEY):
    return main.StorageTile(key, Path.home(), True, provider_override=provider,
                            display_account="someone@example.com")


def _settle(worker):
    assert worker.wait(5000)
    QApplication.processEvents()


def test_no_network_call_runs_on_the_gui_thread(qapp, monkeypatch):
    gui = threading.get_ident()
    seen = []

    def quota(key):
        seen.append(("quota", threading.get_ident()))
        return 1, 4

    def email(key):
        seen.append(("email", threading.get_ident()))
        return "me@dropbox.example"

    monkeypatch.setattr(main.cloud_quota, "quota", quota)
    monkeypatch.setattr(main.cloud_quota, "dropbox_account_email", email)
    tile = _tile(provider="dropbox", key="Dropbox-me")
    _settle(tile._quota_worker)
    assert {name for name, _ in seen} == {"quota", "email"}
    assert all(tid != gui for _, tid in seen), seen
    assert tile.account_lbl.text() == "me@dropbox.example"
    assert tile.pct == 25


def test_tile_builds_fast_while_the_quota_call_is_slow(qapp, monkeypatch, tmp_path):
    _history(tmp_path, [{"ts": "2026-11-19T09:05", "used": 1, "total": 2}])
    release = threading.Event()
    monkeypatch.setattr(main.cloud_quota, "quota",
                        lambda key: (release.wait(10), (3, 4))[1])
    t0 = time.perf_counter()
    tile = _tile()
    built = time.perf_counter() - t0
    assert built < 1.0, built
    # rendered at once from the last known sample, not blank and not local disk
    assert tile.pct == 50 and "as of" in tile.detail_lbl.text()
    release.set()
    _settle(tile._quota_worker)
    assert tile.pct == 75 and "(account quota)" in tile.detail_lbl.text()


def test_placeholder_while_checking_when_no_history(qapp, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(main.cloud_quota, "quota",
                        lambda key: (release.wait(10), (1, 4))[1])
    tile = _tile()
    assert tile.detail_lbl.text() == "Checking account quota…" and tile.pct is None
    release.set()
    _settle(tile._quota_worker)
    assert tile.pct == 25


def test_measured_signal_fires_when_the_worker_finishes(qapp, monkeypatch):
    monkeypatch.setattr(main.cloud_quota, "quota", lambda key: (1, 4))
    tile = _tile()
    got = []
    tile.measured.connect(lambda: got.append(tile.pct))
    _settle(tile._quota_worker)
    assert got == [25]


def test_stale_result_does_not_overwrite_a_newer_one(qapp, monkeypatch):
    gates = [threading.Event(), threading.Event()]
    results = [(1, 10), (9, 10)]
    calls = []
    lock = threading.Lock()

    def quota(key):
        with lock:
            i = len(calls)
            calls.append(i)
        gates[i].wait(10)
        return results[i]

    monkeypatch.setattr(main.cloud_quota, "quota", quota)
    monkeypatch.setattr(main, "_append_quota_sample", lambda *a, **k: None)
    tile = _tile()
    first = tile._quota_worker
    while len(calls) < 1:
        time.sleep(0.01)
    tile.set_usage(Path.home(), True)  # a newer fetch supersedes the first
    second = tile._quota_worker
    gates[1].set()
    _settle(second)
    assert tile.pct == 90
    gates[0].set()  # the old call finishes last
    _settle(first)
    assert tile.pct == 90, "a stale result overwrote the newer one"


def test_retired_tile_ignores_a_late_result(qapp, monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(main.cloud_quota, "quota",
                        lambda key: (release.wait(10), (3, 4))[1])
    tile = _tile()
    before = tile.detail_lbl.text()
    got = []
    tile.measured.connect(lambda: got.append(1))
    w = tile._quota_worker
    tile.retire()
    release.set()
    _settle(w)
    assert tile.detail_lbl.text() == before and tile.pct is None and got == []


def test_refresh_mid_request_drops_the_old_tile_safely(qapp, monkeypatch, tmp_path):
    """StorageCard.refresh() deletes tiles with a fetch in flight: no crash, no stale write."""
    release = threading.Event()
    monkeypatch.setattr(main.cloud_quota, "quota",
                        lambda key: (release.wait(10), (3, 4))[1])
    monkeypatch.setattr(main, "storage_targets",
                        lambda: [(KEY, Path.home(), True)])
    monkeypatch.setattr(main.cloud_quota, "load_manual_accounts", lambda: [])
    monkeypatch.setattr(main.cloud_quota, "provider_for_name", lambda n: "google")
    appended = []
    monkeypatch.setattr(main, "_append_quota_sample", lambda *a, **k: appended.append(a))
    card = main.StorageCard()
    old = [t for t in card.tiles if isinstance(t, main.StorageTile)]
    assert old
    old_workers = [t._quota_worker for t in old]
    card.refresh()
    QApplication.processEvents()  # deleteLater runs
    release.set()
    for w in old_workers:
        _settle(w)
    new = [t for t in card.tiles if isinstance(t, main.StorageTile)]
    for t in new:
        _settle(t._quota_worker)
        assert t.pct == 75
    # only the live tiles' results were applied, never a retired tile's
    assert len(appended) == len(new)


def test_already_queued_stale_result_is_dropped(qapp, monkeypatch):
    """The old worker finished and its result sits in the event queue when a newer fetch
    starts: disconnecting cannot recall it, so the token must drop it."""
    gate = threading.Event()
    n = []

    def quota(key):
        n.append(1)
        if len(n) == 1:
            return 1, 10
        gate.wait(10)
        return 9, 10

    monkeypatch.setattr(main.cloud_quota, "quota", quota)
    monkeypatch.setattr(main, "_append_quota_sample", lambda *a, **k: None)
    tile = _tile()
    first = tile._quota_worker
    assert first.wait(5000)  # finished; its `done` is queued, not yet delivered
    tile.set_usage(Path.home(), True)
    second = tile._quota_worker
    QApplication.processEvents()  # delivers the stale result
    assert tile.pct is None, "stale result applied while a newer fetch was in flight"
    gate.set()
    _settle(second)
    assert tile.pct == 90


def test_superseded_fetch_skips_its_quota_call(qapp, monkeypatch):
    """A retired or replaced fetch must not add network requests once it is cut off."""
    gate = threading.Event()
    in_email = threading.Event()
    emails, quotas = [], []

    def email(key):
        emails.append(1)
        if len(emails) == 1:
            in_email.set()
            gate.wait(10)
        return None

    monkeypatch.setattr(main.cloud_quota, "dropbox_account_email", email)
    monkeypatch.setattr(main.cloud_quota, "quota", lambda key: quotas.append(1) or (1, 4))
    tile = _tile(provider="dropbox", key="Dropbox-me")
    first = tile._quota_worker
    assert in_email.wait(5)
    tile.set_usage(Path.home(), True)
    second = tile._quota_worker
    gate.set()
    _settle(first)
    _settle(second)
    assert len(quotas) == 1, "the superseded fetch still called quota()"


def test_retired_tile_cancels_its_pending_quota_call(qapp, monkeypatch):
    gate = threading.Event()
    in_email = threading.Event()
    quotas = []

    def email(key):
        in_email.set()
        gate.wait(10)

    monkeypatch.setattr(main.cloud_quota, "dropbox_account_email", email)
    monkeypatch.setattr(main.cloud_quota, "quota", lambda key: quotas.append(1) or (1, 4))
    tile = _tile(provider="dropbox", key="Dropbox-me")
    w = tile._quota_worker
    assert in_email.wait(5)
    tile.retire()
    gate.set()
    _settle(w)
    assert quotas == []


def test_gauge_says_checking_not_unavailable_mid_fetch(qapp, monkeypatch, tmp_path):
    from types import SimpleNamespace
    _history(tmp_path, [{"ts": "2026-11-19T09:05", "used": 1, "total": 2}])
    release = threading.Event()

    def quota(key):
        if key != KEY:
            release.wait(10)
        return 1, 4

    monkeypatch.setattr(main.cloud_quota, "quota", quota)
    monkeypatch.setattr(main, "_append_quota_sample", lambda *a, **k: None)
    ok = _tile()
    slow = _tile(key="GoogleDrive-other@example.com")
    _settle(ok._quota_worker)
    window = SimpleNamespace(
        backup_card=SimpleNamespace(proc=None, _dry_run=False),
        tm_card=SimpleNamespace(state={"configured": None}),
        storage_card=SimpleNamespace(tiles=[ok, slow]),
    )
    page = main.OverviewPage(window)
    page.refresh_gauges()
    text = page.gauges["google"].detail_lbl.text()
    assert "1 checking" in text and "unavailable" not in text, text
    release.set()
    _settle(slow._quota_worker)
    page.refresh_gauges()
    assert "checking" not in page.gauges["google"].detail_lbl.text()
