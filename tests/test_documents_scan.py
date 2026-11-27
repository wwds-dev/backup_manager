"""Documents scan: finds large, old, duplicate, rebuildable and scattered items; reads only; never follows
symlinks; skips files not on this Mac; the dialog is report-only (no tick boxes)."""
import builtins
import os
import socket
import subprocess
import time

import pytest

import documents_scan as ds

NOW = time.time()


def write(p, data=b"x", age_days=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    if age_days is not None:
        t = NOW - age_days * 86400
        os.utime(p, (t, t))
    return p


@pytest.fixture
def small(monkeypatch):
    """Shrink thresholds so tests use kilobytes, not gigabytes."""
    monkeypatch.setattr(ds, "LARGE_MIN", 4000)
    monkeypatch.setattr(ds, "OLD_MIN", 2000)
    monkeypatch.setattr(ds, "DUPE_MIN", 1000)
    monkeypatch.setattr(ds, "HEAD_BYTES", 512)


def rels(items):
    return sorted(i["rel"] for i in items)


def test_large_and_old(tmp_path, small):
    write(tmp_path / "A/big.iso", b"a" * 5000)
    write(tmp_path / "A/old.mov", b"b" * 3000, age_days=900)
    write(tmp_path / "A/old_small.txt", b"c" * 100, age_days=900)
    write(tmp_path / "A/new_mid.bin", b"d" * 3000)
    r = ds.scan(tmp_path, now=NOW)
    assert rels(r["large"]) == ["A/big.iso"]
    assert rels(r["old"]) == ["A/old.mov"]
    assert r["old"][0]["age_days"] >= 899


def test_duplicates_need_same_bytes_not_just_size(tmp_path, small):
    same = b"z" * 1500
    write(tmp_path / "A/one.pdf", same)
    write(tmp_path / "B/two.pdf", same)
    write(tmp_path / "C/three.pdf", same)
    write(tmp_path / "D/same_size_other.pdf", b"z" * 1499 + b"y")   # same size, same head, differs at end
    write(tmp_path / "E/tiny1", b"q" * 10)
    write(tmp_path / "E/tiny2", b"q" * 10)                          # below DUPE_MIN
    r = ds.scan(tmp_path, now=NOW, lab_dir=str(tmp_path / "lab"))
    assert len(r["dupes"]) == 1
    g = r["dupes"][0]
    assert g["rels"] == ["A/one.pdf", "B/two.pdf", "C/three.pdf"]
    assert g["count"] == 3 and g["wasted"] == 3000 and not g["in_lab"]
    assert r["totals"]["dupes_outside_lab"] == 3000


def test_hard_links_are_not_duplicates(tmp_path, small):
    a = write(tmp_path / "a.bin", b"h" * 1500)
    os.link(a, tmp_path / "b.bin")
    assert ds.scan(tmp_path, now=NOW)["dupes"] == []


def test_lab_only_duplicates_are_marked(tmp_path, small):
    write(tmp_path / "lab/x/a.png", b"p" * 1500)
    write(tmp_path / "lab/y/a.png", b"p" * 1500)
    r = ds.scan(tmp_path, now=NOW, lab_dir=str(tmp_path / "lab"))
    assert r["dupes"][0]["in_lab"] and r["totals"]["dupes_outside_lab"] == 0


def test_rebuildable_folders_and_venvs(tmp_path, small):
    write(tmp_path / "Proj/node_modules/pkg/index.js", b"n" * 50)
    write(tmp_path / "Course/testenv/pyvenv.cfg", b"home = /x")
    write(tmp_path / "Course/testenv/lib/big.so", b"s" * 5000)
    write(tmp_path / "lab/app/.venv/lib/x.py", b"v")
    r = ds.scan(tmp_path, now=NOW, lab_dir=str(tmp_path / "lab"))
    got = {i["rel"]: i["in_lab"] for i in r["regen"]}
    assert got == {"Proj/node_modules": False, "Course/testenv": False, "lab/app/.venv": True}
    assert r["large"] == []   # files inside a rebuildable folder are not listed again


def test_bundle_and_git_are_one_item(tmp_path, small):
    write(tmp_path / "Apps/Big.app/Contents/a", b"a" * 3000)
    write(tmp_path / "Apps/Big.app/Contents/b", b"a" * 3000)
    write(tmp_path / "repo/.git/objects/x", b"g" * 1500)
    write(tmp_path / "repo/copy_of_x", b"g" * 1500)
    r = ds.scan(tmp_path, now=NOW)
    assert [(i["rel"], i["kind"]) for i in r["large"]] == [("Apps/Big.app", "bundle")]
    assert r["dupes"] == []   # nothing inside .git or a bundle is a duplicate candidate


def test_scattered_folders(tmp_path, small):
    (tmp_path / "Business/OF/Tax").mkdir(parents=True)
    (tmp_path / "Business/Web/Tax").mkdir(parents=True)
    (tmp_path / "Personal/Income Tax/Income Tax 2022").mkdir(parents=True)   # nested: structure
    (tmp_path / "Personal/Income Tax/Income Tax 2023").mkdir(parents=True)
    (tmp_path / "A/Invoices").mkdir(parents=True)
    (tmp_path / "B/invoices copy").mkdir(parents=True)
    (tmp_path / "A/src").mkdir()
    (tmp_path / "B/src").mkdir()                                           # generic name
    (tmp_path / "lab/x/Tax").mkdir(parents=True)                           # the lab is not counted
    r = ds.scan(tmp_path, now=NOW, lab_dir=str(tmp_path / "lab"))
    got = {s["name"]: s["rels"] for s in r["scattered"]}
    assert got == {"tax": ["Business/OF/Tax", "Business/Web/Tax"],
                   "invoices": ["A/Invoices", "B/invoices copy"]}


def test_key_strips_copy_tails():
    assert ds._key("Invoices copy 2") == "invoices"
    assert ds._key("Photos (1)") == "photos"
    assert ds._key("Report_final") == "report"


def test_symlinks_are_not_followed(tmp_path, small):
    outside = tmp_path / "outside"
    write(outside / "huge.bin", b"o" * 5000)
    root = tmp_path / "root"
    root.mkdir()
    os.symlink(outside, root / "link_dir")
    os.symlink(outside / "huge.bin", root / "link_file")
    r = ds.scan(root, now=NOW)
    assert r["large"] == [] and r["totals"]["files"] == 0


def test_dataless_files_are_never_opened(tmp_path, small, monkeypatch):
    write(tmp_path / "a.bin", b"d" * 1500)
    write(tmp_path / "b.bin", b"d" * 1500)
    monkeypatch.setattr(ds, "_dataless", lambda st: True)
    opened = []
    real_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda p, *a, **k: opened.append(p) or real_open(p, *a, **k))
    r = ds.scan(tmp_path, now=NOW)
    assert opened == [] and r["dupes"] == []
    assert any("not downloaded" in n for n in r["notes"])


def test_read_only_no_subprocess_no_network(tmp_path, small, monkeypatch):
    write(tmp_path / "a.bin", b"d" * 1500)
    write(tmp_path / "b.bin", b"d" * 1500)
    modes = []
    real_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda p, mode="r", *a, **k: modes.append(mode) or real_open(p, mode, *a, **k))

    def boom(*a, **k):
        raise AssertionError("not allowed")
    for mod, name in ((subprocess, "run"), (subprocess, "Popen"), (socket, "socket"), (os, "remove"),
                      (os, "unlink"), (os, "rename"), (os, "rmdir")):
        monkeypatch.setattr(mod, name, boom)
    before = sorted(p.name for p in tmp_path.iterdir())
    ds.scan(tmp_path, now=NOW)
    assert set(modes) <= {"rb"} and sorted(p.name for p in tmp_path.iterdir()) == before


def test_entry_cap_and_hash_budget_are_reported(tmp_path, small):
    for i in range(20):
        write(tmp_path / f"f{i}.bin", b"k" * 1500)
    r = ds.scan(tmp_path, now=NOW, entry_cap=5)
    assert any("Stopped after" in n for n in r["notes"])
    r = ds.scan(tmp_path, now=NOW, hash_budget=10)
    assert r["dupes"] == [] and any("budget" in n for n in r["notes"])


def test_scan_safe_turns_a_failure_into_a_note(monkeypatch, tmp_path):
    monkeypatch.setattr(ds, "scan", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    r = ds.scan_safe(tmp_path)
    assert r["large"] == [] and "RuntimeError" in r["notes"][0]


def test_dialog_is_report_only(monkeypatch, tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QPushButton, QTabWidget, QWidget
    import main
    QApplication.instance() or QApplication([])

    class Host(QWidget):
        _documents_ready = main.LabHealthCard._documents_ready
        _doc_table = main.LabHealthCard._doc_table

    seen = {}
    monkeypatch.setattr(QDialog, "exec", lambda self: seen.update(
        boxes=self.findChildren(QCheckBox), tabs=self.findChildren(QTabWidget),
        buttons=[b.text() for b in self.findChildren(QPushButton)]) or 0)
    write(tmp_path / "A/a.bin", b"d" * 1500)
    write(tmp_path / "B/a.bin", b"d" * 1500)
    write(tmp_path / "A/big.iso", b"b" * 5000)
    monkeypatch.setattr(ds, "LARGE_MIN", 4000)
    monkeypatch.setattr(ds, "DUPE_MIN", 1000)
    h = Host()
    h.documents_btn = QPushButton()
    h._documents_ready(ds.scan(tmp_path, now=NOW))
    assert seen["boxes"] == []
    tabs = seen["tabs"][0]
    assert [tabs.tabText(i).split(" (")[0] for i in range(tabs.count())] == [
        "Top folders", "Large", "Old", "Duplicates", "Rebuildable", "Scattered"]
    assert set(seen["buttons"]) <= {"Show in Finder", "Close"}
