"""Lab Health helpers: manifest warning only where one is expected; safe commit."""
import os
import subprocess

import pytest

import lab_health as lh


def _git(p, *a):
    subprocess.run(["git", "-C", str(p), *a], check=True, capture_output=True)


def test_manifest_status(tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("x")
    assert lh.manifest_status(tmp_path / "web") == "n/a"
    (tmp_path / "py").mkdir()
    (tmp_path / "py" / "a.py").write_text("x")
    assert lh.manifest_status(tmp_path / "py") == "missing"
    (tmp_path / "sub" / "app").mkdir(parents=True)
    (tmp_path / "sub" / "app" / "a.py").write_text("x")
    (tmp_path / "sub" / "app" / "pyproject.toml").write_text("")
    assert lh.manifest_status(tmp_path / "sub") == "ok"


def test_venv_python_files_do_not_count(tmp_path):
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "x.py").write_text("x")
    assert lh.manifest_status(tmp_path) == "n/a"


def test_symlinked_project_resolves(tmp_path):
    real = tmp_path / "real"; real.mkdir(); (real / "a.py").write_text("x")
    link = tmp_path / "link"; link.symlink_to(real)
    assert lh.manifest_status(link) == "missing"


def test_ignore_roundtrip(tmp_path):
    f = tmp_path / "i.json"
    assert lh.load_ignored(f) == set()
    lh.save_ignored({"b", "a"}, f)
    assert lh.load_ignored(f) == {"a", "b"}


def test_commit_all_commits_and_blocks_on_secret(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t"); _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.txt").write_text("hello")
    ok, _ = lh.commit_all(tmp_path, "add a")
    assert ok
    (tmp_path / "k.txt").write_text("aws_secret = AKIAIOSFODNN7EXAMPLE9\n"
                                    "token = ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8\n")
    ok, msg = lh.commit_all(tmp_path, "add key")
    log = subprocess.run(["git", "-C", str(tmp_path), "log", "--oneline"],
                         capture_output=True, text=True).stdout
    assert not ok and "secret" in msg and len(log.splitlines()) == 1


def test_empty_message_refused(tmp_path):
    assert lh.commit_all(tmp_path, "  ")[0] is False


# --- Commit acts on the selected row, never a stale currentRow -----------------

_APP = []


@pytest.fixture
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    if not _APP:  # held for the whole run: a collected QApplication segfaults later tests
        _APP.append(QApplication.instance() or QApplication([]))
    return _APP[0]


@pytest.fixture
def card(qapp, monkeypatch):
    """A Lab Health card that never scans the real lab. Kept alive for the whole
    run, like the QApplication: collecting it under a later gc.collect() crashes Qt."""
    import main
    monkeypatch.setattr(main.LabHealthCard, "rescan", lambda self: None)
    monkeypatch.setattr(lh, "load_ignored", lambda path=None: set())
    c = main.LabHealthCard()
    _APP.append(c)
    return c


def _row(name, **kw):
    return {"name": name, "path": f"/x/{name}", "has_git": True, "uncommitted": 0,
            "last_commit": "—", "total_kb": 1, "reclaim_kb": 0, "reclaim_items": [],
            "manifest": "ok", "env_flag": "", "external": False, **kw}


def test_commit_target_needs_one_dirty_selected_row():
    rows = [_row("shopfront"), _row("sonar", uncommitted=3), _row("plain", has_git=False)]
    assert lh.commit_target(rows, []) is None
    assert lh.commit_target(rows, [0]) is None          # clean: nothing to commit
    assert lh.commit_target(rows, [2]) is None          # no repo
    assert lh.commit_target(rows, [0, 1]) is None       # ambiguous
    assert lh.commit_target(rows, [1])["name"] == "sonar"


def test_card_commit_button_follows_selection(card, monkeypatch):
    card._populate([_row("shopfront"), _row("sonar", uncommitted=3)])
    card.table.setCurrentCell(0, 1)  # a stale current row that must not matter
    card.table.clearSelection()
    assert not card.commit_btn.isEnabled()
    card.table.selectRow(0)
    assert not card.commit_btn.isEnabled()
    card.table.selectRow(1)
    assert card.commit_btn.isEnabled() and "sonar" in card.commit_btn.text()
    seen = []
    monkeypatch.setattr(card, "commit_project", lambda info: seen.append(info["name"]))
    card._commit_selected()
    assert seen == ["sonar"]
    assert card.table.horizontalHeaderItem(0).text() == "Clean"


# --- Cleanup never reaches into linked / out-of-tree projects -------------------

def test_is_external(tmp_path):
    root = tmp_path / "active"; root.mkdir()
    (root / "inside").mkdir()
    elsewhere = tmp_path / "elsewhere"; elsewhere.mkdir()
    (root / "linked").symlink_to(elsewhere)
    assert not lh.is_external(root / "inside", root)
    assert lh.is_external(root / "linked", root)


def test_cleanup_targets_skip_external_and_escapes(tmp_path):
    inside = tmp_path / "inside"; (inside / ".venv").mkdir(parents=True)
    outside = tmp_path / "outside"; (outside / ".venv").mkdir(parents=True)
    (inside / "build").symlink_to(outside / ".venv")   # link escaping the project
    rows = [
        _row("inside", path=str(inside), reclaim_kb=2,
             reclaim_items=[(inside / ".venv", 1), (inside / "build", 1), (outside, 1)]),
        _row("syndustryx", path=str(outside), external=True, reclaim_kb=9,
             reclaim_items=[(outside / ".venv", 9)]),
    ]
    targets = lh.cleanup_targets(rows, {0, 1})
    assert [(n, p) for n, p, _ in targets] == [("inside", inside / ".venv")]


def test_card_unticks_external_rows(card, monkeypatch):
    from PySide6.QtCore import Qt
    card._populate([_row("altmerch_store", has_git=False, external=True, reclaim_kb=5),
                    _row("sonar", reclaim_kb=5)])
    ext = card.table.item(0, 0)
    assert not ext.flags() & Qt.ItemIsUserCheckable
    assert "linked" in card.table.item(0, 3).text()
    assert card.table.item(1, 0).checkState() == Qt.Checked
    assert "1 of 2" in card.summary_lbl.text()


def test_git_label_plain_folder_not_red():
    assert lh.git_label(False, 0, "—", external=True) == ("plain folder", "#6b7280")
    assert lh.git_label(False, 0, "—", external=False)[1] == "#dc2626"
    assert lh.git_label(True, 2, "—", False)[0] == "2 uncommitted"
