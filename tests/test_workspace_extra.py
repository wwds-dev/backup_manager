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


@pytest.fixture(autouse=True)
def _no_birth(monkeypatch):
    """The temp folders are born 'now'; tests set ages with utime, so ignore birth/ctime here."""
    monkeypatch.setattr(wx, "_birth", lambda folder: 0.0)


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


def test_copied_snapshot_with_old_mtimes_is_young_by_birth(lab, monkeypatch):
    mk(lab, "backups/copied", 100)
    monkeypatch.setattr(wx, "_birth", lambda folder: NOW - 2 * 86400)   # created two days ago
    r = rows(lab)["copied"]
    assert not r["eligible"] and "2 day" in r["reasons"][0]


def test_walk_cap_means_age_unknown_not_offered(lab, monkeypatch):
    mk(lab, "backups/big", 90)
    monkeypatch.setattr(wx, "_WALK_CAP", 0)
    r = rows(lab)["big"]
    assert not r["eligible"] and r["reasons"][0] == "age unknown"


def test_clamp_days_survives_infinity():
    assert wx.clamp_days(float("inf"), 7, 60, 14) == 14


def test_clean_caches_refuses_repo_and_symlinked_parent(lab, tmp_path):
    (lab / "repo" / ".git").mkdir(parents=True); (lab / "repo" / "__pycache__").mkdir()
    real = tmp_path / "real"; (real / "__pycache__").mkdir(parents=True)
    (lab / "linked").symlink_to(real)
    res = wx.clean_caches([lab / "repo" / "__pycache__", lab / "linked" / "__pycache__"], lab)
    assert not any(ok for _, ok, _ in res)
    assert (lab / "repo" / "__pycache__").exists() and (real / "__pycache__").exists()


def test_script_naming_a_snapshot_blocks_it(lab):
    mk(lab, "backups/snap_a", 50)
    (lab / "active" / "p" / "docs" / "restore.sh").write_text("cp -a backups/snap_a .")
    assert not rows(lab)["snap_a"]["eligible"]


def test_named_pipe_doc_does_not_hang_the_search(lab):
    mk(lab, "backups/snap_a", 50)
    os.mkfifo(lab / "active" / "p" / "docs" / "x.md")
    assert rows(lab)["snap_a"]["eligible"]   # skipped, returns instead of blocking


def test_record_and_report_are_created_private(lab, tmp_path, monkeypatch):
    monkeypatch.setattr(os, "chmod", lambda *a, **k: None)   # prove mode is set at creation
    p = wx.write_report({"a": 1}, tmp_path / "r.json")
    assert (os.stat(p).st_mode & 0o777) == 0o600


def test_hidden_top_folder_cache_is_refused(lab):
    (lab / ".stuff" / "__pycache__").mkdir(parents=True)
    assert not wx.clean_caches([lab / ".stuff" / "__pycache__"], lab)[0][1]


def test_real_birth_time_counts(tmp_path, monkeypatch):
    """Un-stub _birth: a folder created just now is young even when its files look old."""
    monkeypatch.undo()
    d = tmp_path / "lab" / "backups" / "fresh"
    d.mkdir(parents=True)
    f = d / "f.txt"; f.write_text("x")
    os.utime(f, (OLD, OLD)); os.utime(d, (OLD, OLD))
    (tmp_path / "lab" / "active").mkdir()
    r = {x["path"].name: x for x in wx.scan_backups(tmp_path / "lab", now=time.time())}["fresh"]
    assert not r["eligible"] and r["days"] == 0


def test_backup_clamp_upper_bound_and_active_caches(lab):
    assert wx.clamp_days(500, 7, 120, 30) == 120
    (lab / "active" / "__pycache__").mkdir()
    assert not wx.clean_caches([lab / "active" / "__pycache__"], lab)[0][1]


def test_record_never_overwrites_and_report_totals(lab, tmp_path):
    p = mk(lab, "backups/snap_a", 50)
    a = wx.write_backup_record({"path": p, "kb": 1}, tmp_path / "r", NOW)
    b = wx.write_backup_record({"path": p, "kb": 2}, tmp_path / "r", NOW)
    assert a != b and json.loads(a.read_text())["kb"] == 1
    mk(lab, "backups/snap_b", 60, "yy"); (lab / "__pycache__").mkdir()
    rep = wx.build_report(lab, now=NOW, cwds=[])
    assert rep["offered_items"] == 3 and rep["offered_kb"] == (
        rep["backups"]["offered_kb"] + rep["caches"]["kb"])


def test_backups_sorted_offered_first_then_by_size(lab):
    mk(lab, "backups/young", 1, "z" * 9000); mk(lab, "backups/old_small", 50); mk(lab, "backups/old_big", 50, "z" * 9000)
    names = [r["path"].name for r in wx.scan_backups(lab, now=NOW)]
    assert names[-1] == "young" and set(names[:2]) == {"old_small", "old_big"}


def test_report_has_a_lab_root_list_and_is_written_private(lab, tmp_path):
    (lab / "AGENTS.md").write_text("`docs` `p`\n")
    (lab / "docs" / "a.md").write_text("x")
    (lab / "stray.txt").write_text("x")
    rep = wx.build_report(lab, now=NOW, cwds=[])
    assert [(f["rule"], f["rel"]) for f in rep["lab_root"]] == [("R1", "stray.txt")]
    p = wx.write_report(rep, tmp_path / "r.json")
    assert json.loads(p.read_text())["lab_root"][0]["rel"] == "stray.txt"
    assert (os.stat(p).st_mode & 0o777) == 0o600
    assert (lab / "stray.txt").exists()                  # report only: nothing moved
    # offered totals are unchanged by lab-root findings: nothing there is offered
    assert rep["offered_items"] == 0 and rep["offered_kb"] == 0


def test_report_lab_root_empty_for_a_clean_lab(lab):
    (lab / "AGENTS.md").write_text("`docs` `p`\n")
    (lab / "docs" / "a.md").write_text("x")
    assert wx.build_report(lab, now=NOW, cwds=[])["lab_root"] == []


def test_report_survives_a_raising_lab_root_scan(lab, monkeypatch):
    def boom(*a, **k):
        raise ValueError("scan bug")
    monkeypatch.setattr(wx.lab_root_checks, "scan", boom)
    rep = wx.build_report(lab, now=NOW, cwds=[])
    assert [(f["rule"], f["rel"]) for f in rep["lab_root"]] == [("NOTE", ".")]
    assert "failed" in rep["lab_root"][0]["why"]
    assert set(rep) >= {"worktrees", "backups", "archive", "caches", "offered_kb", "offered_items"}
