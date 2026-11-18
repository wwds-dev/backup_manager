"""Slice 2 rules: backups are offered only when old and unreferenced; nothing in a scan deletes."""
import json
import os
import shutil
import time

import pytest

import workspace_extra as wx

NOW = time.time()
OLD = NOW - 40 * 86400


def mk(root, rel, age_days, content="x"):
    d = root / rel
    d.mkdir(parents=True, exist_ok=True)
    f = d / "f.txt"
    f.write_text(content)
    t = NOW - age_days * 86400
    os.utime(f, (t, t)); os.utime(d, (t, t))
    return d


@pytest.fixture
def lab(tmp_path):
    root = tmp_path / "lab"
    (root / "active" / "p" / "docs").mkdir(parents=True)
    (root / "docs").mkdir()
    return root


def rows(lab, **kw):
    return {r["path"].name: r for r in wx.scan_backups(lab, now=NOW, **kw)}


def test_old_unreferenced_backup_is_offered(lab):
    mk(lab, "backups/snap_a", 40)
    assert rows(lab)["snap_a"]["eligible"]


def test_young_backup_is_kept(lab):
    mk(lab, "backups/snap_a", 5)
    r = rows(lab)["snap_a"]
    assert not r["eligible"] and "5 day" in r["reasons"][0]


def test_age_boundary(lab):
    mk(lab, "backups/edge", 30)
    mk(lab, "backups/under", 29)
    r = rows(lab)
    assert r["edge"]["eligible"] and not r["under"]["eligible"]


def test_newest_file_inside_sets_the_age(lab):
    d = mk(lab, "backups/snap_a", 60)
    (d / "new.txt").write_text("n")   # touched now
    assert not rows(lab)["snap_a"]["eligible"]


def test_named_in_project_doc_blocks(lab):
    mk(lab, "backups/sonar-app-prev.noindex", 50)
    (lab / "active" / "p" / "docs" / "audit.md").write_text("keep sonar-app-prev for rollback")
    r = rows(lab)["sonar-app-prev.noindex"]
    assert not r["eligible"] and "audit.md" in r["reasons"][0]


def test_named_in_agents_md_and_todo_blocks(lab):
    mk(lab, "backups/a1", 50); mk(lab, "backups/a2", 50)
    (lab / "AGENTS.md").write_text("see a1")
    (lab / "active" / "p" / "TODO.md").write_text("restore a2")
    r = rows(lab)
    assert not r["a1"]["eligible"] and not r["a2"]["eligible"]


def test_history_doc_lab_notes_readme_and_this_spec_do_not_block(lab):
    mk(lab, "backups/snap_a", 50)
    (lab / "docs" / "history").mkdir()
    (lab / "docs" / "history" / "h.md").write_text("snap_a")
    (lab / "active" / "p" / "docs" / "lab-notes-2026.md").write_text("snap_a")
    (lab / "README.md").write_text("snap_a")
    (lab / "docs" / "workspace-cleanup.md").write_text("snap_a")
    assert rows(lab)["snap_a"]["eligible"]


def test_unreadable_doc_search_fails_closed(lab, monkeypatch):
    mk(lab, "backups/snap_a", 50)
    (lab / "AGENTS.md").write_text("x")
    monkeypatch.setattr(wx, "_FILE_CAP", 0)
    r = rows(lab)["snap_a"]
    assert not r["eligible"] and "search" in r["reasons"][0]


def test_symlinked_snapshot_is_never_offered(lab, tmp_path):
    outside = mk(tmp_path, "elsewhere", 90)
    (lab / "backups").mkdir()
    (lab / "backups" / "link").symlink_to(outside)
    os.utime(lab / "backups" / "link", (OLD, OLD), follow_symlinks=False)   # old link, old target
    assert not rows(lab)["link"]["eligible"]


def test_trash_backup_writes_record_then_moves(lab, tmp_path):
    p = mk(lab, "backups/snap_a", 50)
    moved = []
    ok, msg = wx.trash_backup({"path": p}, lab, lambda s: moved.append(s) or True,
                              out_dir=tmp_path / "rec", now=NOW)
    assert ok and moved == [str(p)] and p.exists()   # fake mover leaves it; real one trashes
    rec = json.loads(next((tmp_path / "rec").glob("*.json")).read_text())
    assert rec["path"] == str(p)
    assert (os.stat(tmp_path / "rec").st_mode & 0o777) == 0o700


def test_trash_backup_rechecks_gates_at_click_time(lab, tmp_path):
    p = mk(lab, "backups/snap_a", 50)
    (lab / "AGENTS.md").write_text("snap_a")     # referenced after the scan
    moved = []
    ok, msg = wx.trash_backup({"path": p}, lab, lambda s: moved.append(s) or True, out_dir=tmp_path / "r", now=NOW)
    assert not ok and not moved and msg.startswith("kept")


def test_no_record_no_trash(lab, tmp_path):
    p = mk(lab, "backups/snap_a", 50)
    blocker = tmp_path / "rec"
    blocker.write_text("a file, so mkdir fails")
    moved = []
    ok, msg = wx.trash_backup({"path": p}, lab, lambda s: moved.append(s) or True, out_dir=blocker, now=NOW)
    assert not ok and not moved and "record" in msg


def test_failed_mover_reports_left_in_place(lab, tmp_path):
    p = mk(lab, "backups/snap_a", 50)
    ok, msg = wx.trash_backup({"path": p}, lab, lambda s: False, out_dir=tmp_path / "r", now=NOW)
    assert not ok and "left in place" in msg


def test_trash_refuses_path_outside_backups(lab, tmp_path):
    p = mk(lab, "docs/stuff", 99)
    moved = []
    ok, _ = wx.trash_backup({"path": p}, lab, lambda s: moved.append(s) or True, out_dir=tmp_path / "r", now=NOW)
    assert not ok and not moved


def test_trash_refuses_nested_path_named_backups(lab, tmp_path):
    p = mk(lab, "active/p/backups/snap", 99)
    moved = []
    ok, _ = wx.trash_backup({"path": p}, lab, lambda s: moved.append(s) or True, out_dir=tmp_path / "r", now=NOW)
    assert not ok and not moved


def test_clamp_days():
    assert wx.clamp_days("abc", 7, 60, 14) == 14
    assert wx.clamp_days(1, 7, 60, 14) == 7 and wx.clamp_days(999, 7, 60, 14) == 60
    assert wx.clamp_days(None, 7, 120, 30) == 30


def test_scan_due():
    assert wx.scan_due(None, NOW) and wx.scan_due("x", NOW)
    assert not wx.scan_due(NOW - 6 * 86400, NOW) and wx.scan_due(NOW - 7 * 86400, NOW)
    assert wx.scan_due(NOW + 1000, NOW)   # clock went backwards


def test_archive_is_listed_with_git_member_verdicts_and_never_offers(lab):
    mk(lab, "archive/old_dir", 90)
    wts = [{"rel": "archive/old_dir/repo", "eligible": False, "reasons": ["1 commit(s) not merged"]}]
    (a,) = wx.scan_archive(lab, wts, now=NOW)
    assert a["days"] >= 89 and a["git_members"][0]["offered"] is False
    assert "eligible" not in a


def test_root_caches_found_but_not_in_agent_or_repo_trees(lab):
    (lab / "__pycache__").mkdir()
    (lab / "scripts" / "__pycache__").mkdir(parents=True)
    (lab / ".claude" / "worktrees" / "w" / "__pycache__").mkdir(parents=True)
    (lab / "active" / "p" / "__pycache__").mkdir()
    (lab / "archive" / "x" / "__pycache__").mkdir(parents=True)
    (lab / "repo" / ".git").mkdir(parents=True)
    (lab / "repo" / "__pycache__").mkdir()
    found = {r["rel"] for r in wx.scan_root_caches(lab)}
    assert found == {"__pycache__", "scripts/__pycache__"}


def test_clean_caches_validates_each_path(lab, tmp_path):
    ok1 = lab / "__pycache__"; ok1.mkdir()
    keep = lab / "active" / "p" / "__pycache__"; keep.mkdir()
    notcache = lab / "scripts"; notcache.mkdir()
    outside = tmp_path / "__pycache__"; outside.mkdir()
    for top in ("active", "archive", "backups"):
        (lab / top / "__pycache__").mkdir(parents=True, exist_ok=True)
    res = wx.clean_caches([ok1, keep, notcache, outside] + [lab / t / "__pycache__" for t in ("active", "archive", "backups")], lab)
    got = {p.name + str(p.parent == lab): ok for p, ok, _ in res}
    assert res[0][1] and not any(r[1] for r in res[1:])
    assert all((lab / t / "__pycache__").exists() for t in ("active", "archive", "backups"))
    assert not ok1.exists() and keep.exists() and notcache.exists() and outside.exists()


def test_clean_caches_refuses_symlink(lab, tmp_path):
    target = tmp_path / "real"; target.mkdir()
    (lab / "__pycache__").symlink_to(target)
    res = wx.clean_caches([lab / "__pycache__"], lab)
    assert not res[0][1] and target.exists()


def test_report_scan_deletes_nothing(lab, monkeypatch):
    mk(lab, "backups/snap_a", 50)
    (lab / "__pycache__").mkdir()
    monkeypatch.setattr(shutil, "rmtree", lambda *a, **k: pytest.fail("report must not delete"))
    monkeypatch.setattr(os, "remove", lambda *a, **k: pytest.fail("report must not delete"))
    rep = wx.build_report(lab, now=NOW, cwds=[])
    assert rep["backups"]["offered"] == 1 and rep["caches"]["folders"] == 1
    assert (lab / "backups" / "snap_a").exists()


def test_write_report_is_mode_600(tmp_path):
    p = wx.write_report({"a": 1}, tmp_path / "d" / "r.json")
    assert (os.stat(p).st_mode & 0o777) == 0o600


def test_symlink_inside_lab_is_never_offered(lab):
    inside = mk(lab, "docs/real", 90)
    (lab / "backups").mkdir()
    (lab / "backups" / "link").symlink_to(inside)
    os.utime(lab / "backups" / "link", (OLD, OLD), follow_symlinks=False)
    assert not rows(lab)["link"]["eligible"]
