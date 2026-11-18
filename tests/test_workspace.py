"""Workspace cleanup rules: a worktree is offered only when every gate passes."""
import os
import subprocess
import time

import pytest

import workspace as ws

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
LATER = time.time() + 40 * 86400   # "now" 40 days on, so nothing is fresh


def git(p, *a):
    return subprocess.run(["git", "-C", str(p), *a], check=True, capture_output=True,
                          text=True, env=ENV).stdout


@pytest.fixture
def lab(tmp_path):
    root = tmp_path / "lab"
    repo = root / "active" / "proj"
    repo.mkdir(parents=True)
    git(repo, "init", "-b", "main")
    (repo / "a.txt").write_text("a")
    git(repo, "add", "a.txt"); git(repo, "commit", "-m", "one")
    return root, repo


def add_wt(repo, name, branch=None):
    path = repo / ".claude" / "worktrees" / name
    if branch:
        git(repo, "worktree", "add", "-b", branch, str(path))
    else:
        git(repo, "worktree", "add", "--detach", str(path))
    return path


def scan(root, **kw):
    kw.setdefault("now", LATER)
    kw.setdefault("cwds", [])
    return {r["path"].name: r for r in ws.scan_worktrees(root, **kw)}


def test_clean_merged_old_worktree_is_offered(lab):
    root, repo = lab
    add_wt(repo, "ok", "feat")
    row = scan(root)["ok"]
    assert row["eligible"] and row["reasons"] == []
    assert row["branch"] == "feat"


def test_dirty_worktree_is_never_offered(lab):
    root, repo = lab
    wt = add_wt(repo, "dirty")
    (wt / "new.txt").write_text("x")           # untracked file counts as uncommitted work
    row = scan(root)["dirty"]
    assert not row["eligible"] and "uncommitted" in row["reasons"][0]


def test_unmerged_commit_blocks(lab):
    root, repo = lab
    wt = add_wt(repo, "ahead", "ahead")
    (wt / "b.txt").write_text("b"); git(wt, "add", "b.txt"); git(wt, "commit", "-m", "two")
    row = scan(root)["ahead"]
    assert not row["eligible"] and any("not merged" in r for r in row["reasons"])
    git(repo, "merge", "ahead")                 # once merged it passes
    assert scan(root)["ahead"]["eligible"]


def test_fresh_worktree_is_treated_as_live(lab):
    root, repo = lab
    add_wt(repo, "fresh")
    row = scan(root, now=time.time())["fresh"]
    assert not row["eligible"] and any("offered after" in r for r in row["reasons"])


def test_process_inside_blocks(lab):
    root, repo = lab
    wt = add_wt(repo, "busy")
    row = scan(root, cwds=[str(wt / "sub")])["busy"]
    assert not row["eligible"] and any("running process" in r for r in row["reasons"])


def test_locked_and_project_folder_worktrees_are_kept(lab):
    root, repo = lab
    wt = add_wt(repo, "locked")
    git(repo, "worktree", "lock", str(wt))
    assert not scan(root)["locked"]["eligible"]
    sibling = root / "active" / "proj-base"       # a worktree that is a project folder
    git(repo, "worktree", "add", "--detach", str(sibling))
    row = scan(root)["proj-base"]
    assert not row["eligible"] and any("project folder" in r for r in row["reasons"])


def test_worktree_outside_lab_root_is_not_listed(lab, tmp_path):
    root, repo = lab
    git(repo, "worktree", "add", "--detach", str(tmp_path / "elsewhere"))
    assert "elsewhere" not in scan(root)


def test_remove_writes_record_then_removes_and_keeps_branch(lab, tmp_path):
    root, repo = lab
    wt = add_wt(repo, "gone", "keepme")
    item = scan(root)["gone"]
    ok, msg = ws.remove_worktree(item, root, cwds=[], now=LATER, out_dir=tmp_path / "rec")
    assert ok, msg
    assert not wt.exists()
    assert "keepme" in git(repo, "branch")
    (rec,) = (tmp_path / "rec").glob("*.json")
    assert "worktree add" in rec.read_text()


def test_remove_rechecks_gates_at_click_time(lab, tmp_path):
    root, repo = lab
    wt = add_wt(repo, "late")
    item = scan(root)["late"]
    assert item["eligible"]
    (wt / "work.txt").write_text("started after the scan")
    ok, msg = ws.remove_worktree(item, root, cwds=[], now=LATER, out_dir=tmp_path / "rec")
    assert not ok and wt.exists() and "uncommitted" in msg
    assert not (tmp_path / "rec").exists()      # no record, nothing touched


def test_no_record_no_removal(lab, tmp_path):
    root, repo = lab
    wt = add_wt(repo, "norec")
    item = scan(root)["norec"]
    blocker = tmp_path / "file"; blocker.write_text("x")   # out_dir is a file: mkdir fails
    ok, msg = ws.remove_worktree(item, root, cwds=[], now=LATER, out_dir=blocker / "sub")
    assert not ok and wt.exists() and "record not saved" in msg


def test_ignored_non_cache_file_blocks_but_caches_do_not(lab):
    root, repo = lab
    (repo / ".gitignore").write_text(".env\nnode_modules/\n__pycache__/\n")
    git(repo, "add", ".gitignore"); git(repo, "commit", "-m", "ignore")
    (repo / "package-lock.json").write_text("{}")   # a manifest says how to rebuild node_modules
    git(repo, "add", "package-lock.json"); git(repo, "commit", "-m", "lock")
    wt = add_wt(repo, "ign")
    (wt / "node_modules").mkdir(); (wt / "node_modules" / "x").write_text("x")
    (wt / "__pycache__").mkdir(); (wt / "__pycache__" / "a.pyc").write_text("x")
    assert scan(root)["ign"]["eligible"]          # caches regenerate
    (wt / ".env").write_text("SECRET=1")          # the only copy of a secret
    row = scan(root)["ign"]
    assert not row["eligible"] and ".env" in row["reasons"][0]


def test_node_modules_without_manifest_blocks(lab):
    root, repo = lab
    (repo / ".gitignore").write_text("node_modules/\nbuild/\n.cache/\n")
    git(repo, "add", ".gitignore"); git(repo, "commit", "-m", "ignore")
    wt = add_wt(repo, "nomani")
    (wt / "node_modules").mkdir(); (wt / "node_modules" / "x").write_text("x")
    row = scan(root)["nomani"]
    assert not row["eligible"] and "no manifest" in row["reasons"][0]


def test_build_dir_holding_a_nested_repo_blocks(lab):
    root, repo = lab
    (repo / ".gitignore").write_text("build/\n")
    (repo / "pyproject.toml").write_text("")
    git(repo, "add", ".gitignore", "pyproject.toml"); git(repo, "commit", "-m", "x")
    wt = add_wt(repo, "nested")
    (wt / "build" / "inner").mkdir(parents=True)
    git(wt / "build" / "inner", "init")           # someone's own repo inside build/
    row = scan(root)["nested"]
    assert not row["eligible"] and "nested git repo" in row["reasons"][0]


def test_unknown_running_processes_blocks(lab):
    root, repo = lab
    add_wt(repo, "blind")
    row = scan(root, cwds=None)["blind"]
    assert not row["eligible"] and any("cannot tell" in r for r in row["reasons"])


def test_cwd_snapshot_failure_returns_none(monkeypatch):
    def boom(*a, **k):
        raise OSError("no lsof")
    monkeypatch.setattr(ws.subprocess, "run", boom)
    assert ws.cwd_snapshot() is None


def test_failed_ignored_status_blocks(lab, monkeypatch):
    root, repo = lab
    wt = add_wt(repo, "gitfail")
    real = ws._git

    def flaky(path, *a, **k):
        if "--ignored" in a:
            return 1, ""
        return real(path, *a, **k)
    monkeypatch.setattr(ws, "_git", flaky)
    row = scan(root)["gitfail"]
    assert not row["eligible"] and "failed" in row["reasons"][0]
    assert wt.exists()


def test_remove_rechecks_right_before_removing(lab, tmp_path, monkeypatch):
    root, repo = lab
    wt = add_wt(repo, "race")
    item = scan(root)["race"]
    calls = {"n": 0}
    real = ws.write_record

    def write_then_dirty(*a, **k):      # work appears between the first check and the removal
        calls["n"] += 1
        (wt / "late.txt").write_text("x")
        return real(*a, **k)
    monkeypatch.setattr(ws, "write_record", write_then_dirty)
    ok, msg = ws.remove_worktree(item, root, cwds=[], now=LATER, out_dir=tmp_path / "rec")
    assert not ok and wt.exists() and "uncommitted" in msg


def test_default_branch_not_the_checked_out_feature_branch(lab):
    root, repo = lab
    git(repo, "checkout", "-b", "feature")      # main worktree sits on a feature branch
    wt = add_wt(repo, "wt")
    (wt / "c.txt").write_text("c"); git(wt, "add", "c.txt"); git(wt, "commit", "-m", "c")
    assert ws.default_branch(repo) == "main"


def test_newline_in_a_worktree_path_cannot_forge_another_entry():
    out = ("worktree /lab/active/proj\0HEAD aaa\0branch refs/heads/main\0\0"
           "worktree /lab/x\nworktree /lab/active/victim\0HEAD bbb\0detached\0\0")
    blocks = ws.parse_worktrees(out)
    assert [b["path"] for b in blocks] == ["/lab/active/proj", "/lab/x\nworktree /lab/active/victim"]


def test_repo_config_cannot_run_commands_through_git(lab, tmp_path):
    root, repo = lab
    wt = add_wt(repo, "cfg")
    marker = tmp_path / "ran"
    git(repo, "config", "core.fsmonitor", f"touch {marker}; echo")
    git(repo, "config", "core.hooksPath", str(tmp_path / "hooks"))
    scan(root)
    assert not marker.exists()
    assert wt.exists()


def test_restore_record_is_private(lab, tmp_path):
    root, repo = lab
    add_wt(repo, "priv")
    item = scan(root)["priv"]
    path = ws.write_record(item, tmp_path / "rec")
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert oct((tmp_path / "rec").stat().st_mode & 0o777) == "0o700"


def test_worktree_list_asks_git_for_nul_separated_output(lab):
    root, repo = lab
    seen = []
    real = subprocess.run

    def spy(cmd, *a, **k):
        seen.append(cmd)
        return real(cmd, *a, **k)
    ws.list_worktrees(root, runner=spy)
    assert any("worktree" in c and "list" in c and "-z" in c for c in seen)
    assert all("core.hooksPath=/dev/null" in c for c in seen)
