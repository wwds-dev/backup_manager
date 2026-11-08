"""Lab Health helpers: manifest warning only where one is expected; safe commit."""
import json
import os
import subprocess

import pytest
from pathlib import Path

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
    monkeypatch.setattr(lh, "load_settings", lambda path=None: {
        "env_idle_days": 7, "project_idle_days": 30})
    monkeypatch.setattr(lh, "ENV_IDLE_DAYS", 7)
    monkeypatch.setattr(lh, "IDLE_DAYS", 30)
    c = main.LabHealthCard()
    _APP.append(c)
    return c


def _row(name, **kw):
    return {"name": name, "path": f"/x/{name}", "has_git": True, "uncommitted": 0,
            "last_commit": "—", "total_kb": 1, "reclaim_kb": 0, "items": [], "idle_days": 90,
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
    assert card.table.horizontalHeaderItem(0).text() == "Caches"


# --- Cleanup never reaches into linked / out-of-tree projects -------------------

def test_is_external(tmp_path):
    root = tmp_path / "active"; root.mkdir()
    (root / "inside").mkdir()
    elsewhere = tmp_path / "elsewhere"; elsewhere.mkdir()
    (root / "linked").symlink_to(elsewhere)
    assert not lh.is_external(root / "inside", root)
    assert lh.is_external(root / "linked", root)


def _item(path, kind="env", eligible=True, kb=1, rebuild="uv sync"):
    return {"path": path, "kb": kb, "kind": kind, "rebuild": rebuild,
            "eligible": eligible, "reason": "" if eligible else "locked"}


def test_cleanup_targets_skip_external_and_escapes(tmp_path):
    inside = tmp_path / "inside"; (inside / ".venv").mkdir(parents=True)
    outside = tmp_path / "outside"; (outside / ".venv").mkdir(parents=True)
    (inside / "build").symlink_to(outside / ".venv")   # link escaping the project
    rows = [
        _row("inside", path=str(inside), reclaim_kb=2,
             items=[_item(inside / ".venv"), _item(inside / "build"), _item(outside)]),
        _row("syndustryx", path=str(outside), external=True, reclaim_kb=9,
             items=[_item(outside / ".venv")]),
    ]
    targets = lh.cleanup_targets(rows, {0, 1}, {0, 1})
    assert [(t["project"], t["path"]) for t in targets] == [("inside", inside / ".venv")]


def test_cleanup_targets_split_by_ticked_column_and_eligibility(tmp_path):
    proj = tmp_path / "p"; (proj / "__pycache__").mkdir(parents=True)
    (proj / ".venv").mkdir(); (proj / "node_modules").mkdir()
    rows = [_row("p", path=str(proj), items=[
        _item(proj / "__pycache__", kind="junk", rebuild=None),
        _item(proj / ".venv"),
        _item(proj / "node_modules", eligible=False)])]
    names = lambda t: sorted(x["path"].name for x in t)  # noqa: E731
    assert names(lh.cleanup_targets(rows, {0}, set())) == ["__pycache__"]
    assert names(lh.cleanup_targets(rows, set(), {0})) == [".venv"]   # locked env never
    assert names(lh.cleanup_targets(rows, {0}, {0})) == [".venv", "__pycache__"]
    assert lh.cleanup_targets(rows, set(), set()) == []


def test_rebuild_command(tmp_path):
    py = tmp_path / "py"; (py / ".venv").mkdir(parents=True)
    assert lh.rebuild_command(py, py / ".venv") is None            # no manifest
    (py / "requirements.txt").write_text("x")
    assert lh.rebuild_command(py, py / ".venv") == "pip install -r requirements.txt"
    (py / "uv.lock").write_text("")
    assert lh.rebuild_command(py, py / ".venv") == "uv sync"
    js = tmp_path / "js"; (js / "node_modules").mkdir(parents=True)
    assert lh.rebuild_command(js, js / "node_modules") is None
    (js / "package-lock.json").write_text("{}")
    assert lh.rebuild_command(js, js / "node_modules") == "npm ci"


def test_classify_item_idle_and_rebuild_gates(tmp_path):
    proj = tmp_path / "p"; (proj / ".venv").mkdir(parents=True); (proj / "build").mkdir()
    (proj / "pyproject.toml").write_text("")
    now = 1_000_000_000.0
    old, recent = now - (lh.ENV_IDLE_DAYS + 1) * 86400, now - 86400
    junk = lh.classify_item(proj, proj / "__pycache__", 5, 0)
    assert junk["kind"] == "junk" and junk["eligible"]              # safe even if active
    idle = lh.ENV_IDLE_DAYS
    venv = lambda **kw: lh.classify_item(proj, proj / ".venv", 5, idle, now=now, **kw)  # noqa: E731
    # the project's own root env counts as used while the project is active
    own = lh.classify_item(proj, proj / ".venv", 5, 0, last_use=old, now=now)
    assert not own["eligible"] and "project files edited" in own["reason"]
    # any recent evidence (here: tests run) locks an env whose own files look old
    ev = venv(last_use=old, evidence=[(recent, "tests run (.pytest_cache)")])
    assert not ev["eligible"] and "tests run" in ev["reason"]
    assert ev["last_use"] == recent and ev["last_use_source"].startswith("tests run")
    # ...but a second env (worktree, sub-tool) unused for a week is offered anyway
    extra = proj / ".claude" / "worktrees" / "w" / ".venv"; extra.mkdir(parents=True)
    assert lh.classify_item(proj, extra, 5, 0, last_use=old, now=now)["eligible"]
    assert venv(last_use=old)["eligible"]
    r = venv(last_use=recent)
    assert not r["eligible"] and "used 1 day ago" in r["reason"]
    unknown = lh.classify_item(proj, proj / ".venv", 5, None, last_use=None, now=now)
    assert not unknown["eligible"] and unknown["reason"] == "last use unknown"
    busy = venv(last_use=old, users=["running process python (pid 7)"])
    assert not busy["eligible"] and "in use" in busy["reason"] and "pid 7" in busy["reason"]
    # build/dist keep the project-idle rule
    assert not lh.classify_item(proj, proj / "build", 5, lh.IDLE_DAYS - 1)["eligible"]
    assert not lh.classify_item(proj, proj / "build", 5, None)["eligible"]
    assert lh.classify_item(proj, proj / "build", 5, lh.IDLE_DAYS)["eligible"]
    (proj / "pyproject.toml").unlink()
    locked = venv(last_use=old)
    assert not locked["eligible"] and "rebuilt" in locked["reason"]


def test_env_last_use_reads_bin_and_cfg(tmp_path):
    env = tmp_path / ".venv"; (env / "bin").mkdir(parents=True)
    (env / "bin" / "python").write_text(""); (env / "pyvenv.cfg").write_text("")
    for p in (env / "bin" / "python", env / "bin", env / "pyvenv.cfg"):
        os.utime(p, (100, 100))
    os.utime(env / "bin" / "python", (100, 5000))
    assert lh.env_last_use(env) == 5000
    assert lh.env_last_use(tmp_path / "nothing") is None


def test_env_users_process_launchd_and_app(tmp_path):
    proj = tmp_path / "sonar"; env = proj / ".venv"; (env / "bin").mkdir(parents=True)
    other = tmp_path / "sonar-old" / ".venv"; other.mkdir(parents=True)
    procs = [(11, "python", f"{env}/bin/python main.py"),
             (12, "Python", f"{env}/lib/python3.12/site-packages/x.so"),
             (12, "Python", f"{env}/lib/y.so"),                 # same pid counted once
             (13, "python", f"{other}/bin/python")]              # prefix is not a match
    jobs = {"com.x.sonar.plist": [f"{env}/bin/python", "-m", "sonar"],
            "com.x.script.plist": [f"{proj}/run.sh"],
            "com.x.unrelated.plist": [str(tmp_path)]}
    apps = {"Sonar": str(proj.resolve()), "Other": str(tmp_path / "x")}
    users = lh.env_users(env, proj, procs, jobs, apps)
    assert sum("pid 11" in u for u in users) == 1 and sum("pid 12" in u for u in users) == 1
    assert not any("pid 13" in u for u in users)
    assert "launchd job com.x.sonar.plist" in users
    assert any("com.x.script.plist" in u and "this project" in u for u in users)
    assert not any("unrelated" in u for u in users)
    assert "Sonar.app (launches from this checkout)" in users and len(users) == 5
    # the root node_modules of an app's checkout is locked too (its server runs from it)
    nm = proj / "node_modules"; nm.mkdir()
    assert any("Sonar.app" in u for u in lh.env_users(nm, proj, [], {}, apps))
    sub = proj / "web" / "node_modules"; sub.mkdir(parents=True)
    assert lh.env_users(sub, proj, [], jobs, apps) == []
    assert lh.env_users(other, other.parent, procs[:3], jobs, apps) == []


def test_never_offer_self_hub_and_bundle_envs(tmp_path):
    proj = tmp_path / "imprint"; env = proj / ".venv"; (env / "bin").mkdir(parents=True)
    # the running app's own interpreter
    assert any("this app" in u for u in lh.env_users(env, proj, self_paths=[str(env.resolve())]))
    # a Lab Hub app run from source; one that runs a built bundle does not count
    hub = [{"key": "imprint", "name": "Imprint", "project": os.path.realpath(proj),
            "from_source": True}]
    assert lh.env_users(env, proj, hub=hub) == ["Lab Hub app Imprint runs from this checkout"]
    assert lh.env_users(env, proj, hub=[{**hub[0], "from_source": False}]) == []
    # a bundle whose launcher names the env, or a script in the checkout
    assert lh.env_users(env, proj, bundles={"X": [f"{env}/bin/python"]}) == \
        ["X.app names it in its launcher"]
    assert lh.env_users(env, proj, bundles={"Y": [f"{proj}/main.py"]}) == \
        ["Y.app launches from this checkout"]
    # ...and classify_item never offers it, however idle
    item = lh.classify_item(proj, env, 5, None, last_use=1.0, now=10**9,
                            users=lh.env_users(env, proj, hub=hub))
    (proj / "requirements.txt").write_text("x")
    item = lh.classify_item(proj, env, 5, None, last_use=1.0, now=10**9,
                            users=lh.env_users(env, proj, hub=hub))
    assert not item["eligible"] and "Lab Hub app Imprint" in item["reason"]


def test_lab_hub_apps_and_bundle_references(tmp_path):
    toml = tmp_path / "lab_hub" / "lab_hub" / "apps.toml"; toml.parent.mkdir(parents=True)
    toml.write_text('[[suites]]\nkey="imprint"\nname="Imprint"\nproject="imprint"\n'
                    'entry="main.py"\n\n[[suites]]\nkey="s"\nname="S"\nproject="s"\n'
                    'entry="x.py"\nruns_from_source=false\n')
    apps = lh.lab_hub_apps(tmp_path)
    assert [(a["key"], a["from_source"]) for a in apps] == [("imprint", True), ("s", False)]
    assert apps[0]["project"] == os.path.realpath(tmp_path / "imprint")
    assert lh.lab_hub_apps(tmp_path / "none") == []
    macos = tmp_path / "Apps" / "X.app" / "Contents" / "MacOS"; macos.mkdir(parents=True)
    (macos / "X").write_text('#!/bin/sh\nexec "/Users/me/lab/x/.venv/bin/python" main.py\n')
    assert lh.bundle_references(tmp_path / "Apps") == {"X": ["/Users/me/lab/x/.venv/bin/python"]}


def test_use_evidence_sources(tmp_path):
    proj = tmp_path / "sonar"; env = proj / ".venv"; env.mkdir(parents=True)
    (proj / "pkg" / "__pycache__").mkdir(parents=True)
    pyc = proj / "pkg" / "__pycache__" / "a.cpython-311.pyc"; pyc.write_text("")
    os.utime(pyc, (500, 500))
    inside = env / "lib" / "__pycache__"; inside.mkdir(parents=True)     # env's own: ignored
    (inside / "z.pyc").write_text(""); os.utime(inside / "z.pyc", (900, 900))
    (proj / ".pytest_cache" / "v").mkdir(parents=True)
    (proj / ".pytest_cache" / "v" / "x").write_text(""); os.utime(proj / ".pytest_cache" / "v" / "x", (600, 600))
    (proj / "logs").mkdir(); (proj / "logs" / "app.log").write_text("")
    os.utime(proj / "logs" / "app.log", (700, 700))
    usage = {"hub_logs": {os.path.realpath(proj): 800.0},
             "history": [(850.0, "cd ~/Documents/lab/active/sonar && python main.py"),
                         (999.0, "cd sonar-old")]}
    ev = dict((label, t) for t, label in lh.use_evidence(env, usage))
    assert ev["Python bytecode compiled from its sources"] == 500
    assert ev["tests run (.pytest_cache)"] == 600 and ev["log file written"] == 700
    assert ev["launched from Lab Hub"] == 800 and ev["named in shell history"] == 850
    assert lh.use_evidence(env, usage)[0] == (850.0, "named in shell history")


def test_shell_history_and_launch_times(tmp_path):
    z = tmp_path / ".zsh_history"
    z.write_text(": 1700000000:0;cd /p/sonar\n" + "old\n" * 400 + "cd /p/imprint\n")
    os.utime(z, (1800000000, 1800000000))
    h = lh.shell_history([z, tmp_path / "missing"])
    assert (1700000000.0, "cd /p/sonar") in h and (1800000000.0, "cd /p/imprint") in h
    assert len(h) == 1 + lh.HISTORY_RECENT_LINES          # untimestamped: only the tail
    log = tmp_path / "lab-hub-launch-sonar.log"; log.write_text(""); os.utime(log, (42, 42))
    assert lh.lab_hub_launch_times([{"key": "sonar", "project": "/p/sonar"},
                                    {"key": "none", "project": "/p/x"}], tmp_path) == \
        {"/p/sonar": 42}


def test_recall_use_survives_cache_cleanup(tmp_path):
    env = tmp_path / ".venv"; mem = {}
    assert lh.recall_use(env, [(500.0, "tests run")], mem)[0] == (500.0, "tests run")
    later = lh.recall_use(env, [], mem)                   # caches deleted since
    assert later[0][0] == 500.0 and "earlier scan" in later[0][1]
    f = tmp_path / "mem.json"; lh.save_use_memory(mem, f)
    assert lh.load_use_memory(f) == mem and lh.load_use_memory(tmp_path / "no") == {}


def test_rebuild_record_and_rebuild(tmp_path, monkeypatch):
    proj = tmp_path / "imprint"; env = proj / ".venv"; (env / "bin").mkdir(parents=True)
    (env / "pyvenv.cfg").write_text("home = /x\nversion_info = 3.11.15\n")
    (proj / "pyproject.toml").write_text("")
    monkeypatch.setattr(lh, "_uv", lambda: "/u/uv")
    calls = []

    class R:
        def __init__(self, rc=0, out=""):
            self.returncode, self.stdout, self.stderr = rc, out, ""

    def run(argv, **kw):
        calls.append((argv, kw.get("cwd")))
        if argv[1:3] == ["pip", "freeze"]:
            return R(0, "requests==2.31.0\n-e file:///x/imprint\nidna==3.6\n")
        if argv[-2:] and "-r" in argv:
            calls.append(("freeze-file", Path(argv[-1]).read_text()))
        return R()
    target = {"path": env, "project": "imprint", "rebuild": "uv sync", "kb": 10,
              "last_use": 5.0, "last_use_source": "tests run"}
    out = tmp_path / "records"
    f = lh.write_rebuild_record(target, proj, out, runner=run, now=1000)
    rec = json.loads(f.read_text())
    assert rec["python"] == "3.11" and rec["freeze"][0] == "requests==2.31.0"
    assert rec["kind"] == "python" and rec["rebuild"] == "uv sync"
    assert lh.missing_env_records(out) == []              # env still there
    import shutil
    shutil.rmtree(env)                                    # (test fixture, not the app)
    missing = lh.missing_env_records(out)
    assert [m["env_path"] for m in missing] == [str(env)]
    calls.clear()
    ok, msg = lh.rebuild_from_record(missing[0], runner=run, now=2000)
    assert ok and msg == "exact versions"
    argvs = [c[0] for c in calls if c[0] != "freeze-file"]
    assert argvs[0][:4] == ["/u/uv", "venv", "--allow-existing", "--python"]
    assert "-r" in argvs[1] and argvs[2][-2:] == ["-e", str(proj)]   # editable from checkout
    frozen = [c[1] for c in calls if c[0] == "freeze-file"][0]
    assert "requests==2.31.0" in frozen and "idna==3.6" in frozen and "file://" not in frozen
    assert json.loads(f.read_text())["rebuilt_at"] == 2000
    # a failed rebuild is marked, reported, and offered again; nothing is removed
    env.mkdir()
    bad = lambda argv, **kw: R(1, "no network")  # noqa: E731
    rec2 = {**missing[0], "failed": "x"}
    ok, msg = lh.rebuild_from_record(rec2, runner=bad)
    assert not ok and "no network" in msg and env.exists()
    assert lh.rebuild_from_record({**rec2, "project_path": str(tmp_path / "gone")})[0] is False


def test_record_lost_env(tmp_path, monkeypatch):
    monkeypatch.setattr(lh, "_uv", lambda: "/u/uv")
    proj = tmp_path / "sonar"; proj.mkdir(); (proj / "requirements.txt").write_text("x")
    out = tmp_path / "rec"
    f = lh.record_lost_env("sonar", proj, proj / ".venv", kb=9, python="3.11", out_dir=out)
    rec = json.loads(f.read_text())
    assert rec["rebuild"] == "pip install -r requirements.txt" and rec["freeze"] is None
    assert [m["env_path"] for m in lh.missing_env_records(out)] == [str(proj / ".venv")]
    plan = lh.rebuild_plan(rec)
    assert plan[0][0][-3:] == ["--python", "3.11", str(proj / ".venv")]
    (proj / ".venv").mkdir()
    with pytest.raises(ValueError):                         # still there: no record
        lh.record_lost_env("sonar", proj, proj / ".venv", out_dir=out)
    with pytest.raises(ValueError):                         # nothing to rebuild from
        lh.record_lost_env("x", tmp_path, tmp_path / "node_modules", out_dir=out)


def test_rebuild_plan_without_freeze(tmp_path, monkeypatch):
    monkeypatch.setattr(lh, "_uv", lambda: "/u/uv")
    base = {"env_path": str(tmp_path / "p" / ".venv"), "kind": "python", "python": "3.11",
            "freeze": None}
    plan = lh.rebuild_plan({**base, "rebuild": "uv sync"})
    assert plan[1][0] == ["/u/uv", "sync"] and plan[1][2] == {
        "UV_PROJECT_ENVIRONMENT": base["env_path"]}
    plan = lh.rebuild_plan({**base, "rebuild": "pip install -r requirements.txt"})
    assert plan[1][0][-2:] == ["-r", "requirements.txt"] and plan[1][0][1:3] == ["pip", "install"]
    node = lh.rebuild_plan({"env_path": str(tmp_path / "w" / "node_modules"), "kind": "node",
                            "rebuild": "npm ci"})
    assert node == [(["npm", "ci"], str(tmp_path / "w"), {})]


def test_card_select_safe_ticks_caches_only(card):
    from PySide6.QtCore import Qt
    row = _row("sonar", reclaim_kb=6, items=[
        _item(Path("/x/sonar/__pycache__"), kind="junk", kb=1, rebuild=None),
        _item(Path("/x/sonar/.venv"), kb=5)])                          # offered env
    card._populate([row])
    assert card.table.item(0, 1).flags() & Qt.ItemIsUserCheckable
    card.toggle_safe()
    assert card.table.item(0, 0).checkState() == Qt.Checked
    assert card.table.item(0, 1).checkState() == Qt.Unchecked          # env needs its own tick


def test_env_confirm_line_shows_evidence_and_cost():
    t = {"path": Path("/x/sonar/.venv"), "project": "sonar", "rebuild": "uv sync",
         "last_use": 0.0 + 1, "last_use_source": "tests run (.pytest_cache)"}
    line = lh.env_confirm_line(t, "1.2 GB", now=1 + 9 * 86400)
    assert "last used 9 days ago (tests run" in line and "rebuild: uv sync" in line
    assert "re-downloads about 1.2 GB" in line
    assert "no sign of use" in lh.env_confirm_line({**t, "last_use": None}, "1 MB")


def test_process_snapshot_leaves_out_the_scanner(monkeypatch):
    me = os.getpid()

    class R:
        def __init__(self, out):
            self.stdout = out
    outs = iter([R(f"{me} /p/.venv/bin/python scan\n7 /q/.venv/bin/python app\n"),
                 R(f"p{me}\ncPython\nn/p/.venv/lib/x.so\np7\ncPython\nn/q/.venv/lib/y.so\n")])
    monkeypatch.setattr(lh.subprocess, "run", lambda *a, **k: next(outs))
    assert {pid for pid, _, _ in lh.process_snapshot()} == {7}


def test_launchd_jobs_and_app_roots(tmp_path):
    import plistlib
    d = tmp_path / "agents"; d.mkdir()
    (d / "a.plist").write_bytes(plistlib.dumps(
        {"Label": "a", "ProgramArguments": ["/p/.venv/bin/python", "x.py"]}, fmt=plistlib.FMT_BINARY))
    (d / "broken.plist").write_text("not a plist /q/.venv")
    jobs = lh.launchd_jobs([d, tmp_path / "missing"])
    assert "/p/.venv/bin/python" in jobs["a.plist"] and "/q/.venv" in jobs["broken.plist"][0]
    res = tmp_path / "Apps" / "Sonar.app" / "Contents" / "Resources"; res.mkdir(parents=True)
    (res / "project_root.txt").write_text(f"{tmp_path}\n")
    assert lh.app_project_roots(tmp_path / "Apps") == {"Sonar": os.path.realpath(tmp_path)}


def test_manifest_hash_and_duplicates(tmp_path):
    rows = []
    for name, mtime, reqs in (("imprint", 300, "b==2\na==1\n"),
                              ("imprint-base", 100, "# pinned\na==1\nb==2\n"),
                              ("imprint-deps", 200, "a==1\nb==2"), ("solo", 50, "c==3")):
        p = tmp_path / name; (p / ".venv").mkdir(parents=True)
        (p / "requirements.txt").write_text(reqs)
        item = lh.classify_item(p, p / ".venv", 5, None, last_use=mtime, now=10**7)
        item["manifest_hash"] = lh.manifest_hash(p, p / ".venv")
        rows.append({"items": [item]})
    hashes = {r["items"][0]["manifest_hash"] for r in rows[:3]}
    assert len(hashes) == 1 and next(iter(hashes)).startswith("requirements.txt:")
    lh.mark_duplicates(rows)
    imprint, base, deps, solo = (r["items"][0] for r in rows)
    assert base["oldest"] and not imprint["oldest"] and not deps["oldest"]
    assert len(base["duplicates"]) == 2 and "duplicates" not in solo
    line = lh.env_tooltip_line(base, "1.5 GB", now=100 + 3 * 86400)
    assert "same manifest as" in line and "oldest copy" in line and "last used 3 days" in line
    assert "rebuild: pip install -r requirements.txt" in line
    # drifted pins: no exact match, but the same package list still groups them
    a, b = tmp_path / "a", tmp_path / "b"
    for p, reqs, t in ((a, "Foo_Bar==1\nbaz>=2\n", 10), (b, "foo-bar==3\nbaz==2.5\n", 20)):
        (p / ".venv").mkdir(parents=True); (p / "requirements.txt").write_text(reqs)
    ia, ib = ({"kind": "env", "path": p / ".venv", "last_use": t, "eligible": True,
               "manifest_hash": lh.manifest_hash(p, p / ".venv"),
               "package_set_hash": lh.package_set_hash(p, p / ".venv")}
              for p, t in ((a, 10), (b, 20)))
    assert ia["manifest_hash"] != ib["manifest_hash"]
    lh.mark_duplicates([{"items": [ia, ib]}])
    assert ia["oldest"] and ia["dup_kind"] == "same packages, other versions"
    ia["eligible"] = False; del ia["duplicates"]; del ib["duplicates"]
    lh.mark_duplicates([{"items": [ia, ib]}])
    assert not ia["oldest"] and ib["oldest"]                     # a locked env is never "remove this"
    assert lh.manifest_hash(a, a / "build") is None                # build/dist never grouped
    (tmp_path / "solo" / "uv.lock").write_text("x")             # uv.lock wins
    assert lh.manifest_hash(tmp_path / "solo", tmp_path / "solo" / ".venv").startswith("uv.lock:")
    assert lh.manifest_hash(tmp_path, tmp_path / ".venv") is None


def test_card_env_tooltip_shows_users_and_rebuild(card):
    used = _item(Path("/x/sonar/.venv"), kb=5, eligible=False)
    used.update(reason="in use: Sonar.app (launches from this checkout)",
                users=["Sonar.app (launches from this checkout)"])
    free = _item(Path("/x/sonar/node_modules"), kb=3, rebuild="npm ci")
    card._populate([_row("sonar", reclaim_kb=8, items=[used, free])])
    tip = card.table.item(0, 1).toolTip()
    assert "Sonar.app" in tip and "rebuild: uv sync" in tip and "rebuild: npm ci" in tip


def test_idle_days_ignores_caches_and_ds_store(tmp_path):
    import os, time
    proj = tmp_path / "p"; proj.mkdir()
    src = proj / "a.py"; src.write_text("x")
    now = time.time()
    os.utime(src, (now - 40 * 86400, now - 40 * 86400))
    (proj / ".DS_Store").write_text("x")
    (proj / "__pycache__").mkdir(); (proj / "__pycache__" / "a.pyc").write_text("x")
    assert lh.idle_days(proj, now) == 40
    assert lh.idle_days(tmp_path / "empty", now) is None


def test_card_starts_unticked_and_offers_only_eligible(card):
    from PySide6.QtCore import Qt
    row = _row("sonar", reclaim_kb=6, items=[
        _item(Path("/x/sonar/__pycache__"), kind="junk", kb=1, rebuild=None),
        _item(Path("/x/sonar/.venv"), kb=5, eligible=False)])
    ext = _row("altmerch_store", has_git=False, external=True, reclaim_kb=5,
               items=[_item(Path("/x/alt/.venv"), kb=5)])
    card._populate([ext, row])
    flag = Qt.ItemIsUserCheckable
    assert not card.table.item(0, 0).flags() & flag and not card.table.item(0, 1).flags() & flag
    assert card.table.item(1, 0).flags() & flag
    assert card.table.item(1, 0).checkState() == Qt.Unchecked     # nothing pre-ticked
    assert not card.table.item(1, 1).flags() & flag               # locked env
    assert card.table.item(1, 1).text().startswith("\U0001F512")
    assert "never cleaned" in card.table.item(0, 0).toolTip()
    assert "safe to clean now" in card.summary_lbl.text()
    red = lambda i: i.foreground().color().name() == "#ef4444"  # noqa: E731
    assert not red(card.table.item(1, 0)) and not red(card.table.item(1, 2))
    card.toggle_safe()
    assert card.table.item(1, 0).checkState() == Qt.Checked
    assert red(card.table.item(1, 0)) and red(card.table.item(1, 2))   # will be deleted
    assert not red(card.table.item(1, 1))                              # locked env stays
    assert "Will delete" in card.ticked_lbl.text()
    card.toggle_safe()
    assert card.table.item(1, 0).checkState() == Qt.Unchecked
    assert not red(card.table.item(1, 0)) and not red(card.table.item(1, 2))
    assert card.ticked_lbl.text() == ""


def test_git_label_plain_folder_not_red():
    assert lh.git_label(False, 0, "—", external=True) == ("plain folder", "#6b7280")
    assert lh.git_label(False, 0, "—", external=False)[1] == "#dc2626"
    assert lh.git_label(True, 2, "—", False)[0] == "2 uncommitted"


# --- Commit warnings and multi-select commit -----------------------------------

def _repo(p):
    _git(p, "init", "-q"); _git(p, "config", "user.email", "t@t"); _git(p, "config", "user.name", "t")
    (p / "a.txt").write_text("a"); _git(p, "add", "-A"); _git(p, "commit", "-qm", "init")


def test_commit_warnings_clean_repo(tmp_path):
    _repo(tmp_path)
    (tmp_path / "b.txt").write_text("b")
    assert lh.commit_warnings(tmp_path) == []


def test_commit_warnings_flags_risks(tmp_path):
    _repo(tmp_path)
    (tmp_path / ".env").write_text("X=1")
    (tmp_path / ".env.example").write_text("X=")
    (tmp_path / "node_modules" / "p").mkdir(parents=True)
    (tmp_path / "node_modules" / "p" / "i.js").write_text("x")
    (tmp_path / "big.bin").write_bytes(b"0" * (lh.BIG_FILE_MB * 1024 * 1024 + 1))
    w = "\n".join(lh.commit_warnings(tmp_path))
    assert ".env" in w and ".env.example" not in w
    assert "node_modules" in w and "big.bin" in w


def test_commit_warnings_mid_merge_and_detached(tmp_path):
    _repo(tmp_path)
    _git(tmp_path, "checkout", "-q", "--detach")
    (tmp_path / ".git" / "MERGE_HEAD").write_text("x")
    (tmp_path / "c.txt").write_text("c")
    w = "\n".join(lh.commit_warnings(tmp_path))
    assert "merge" in w.lower() and "Detached" in w


def test_commit_targets_all_dirty_selected_rows():
    rows = [_row("a", uncommitted=2), _row("b"), _row("c", uncommitted=1),
            _row("d", uncommitted=4, external=True), _row("e", has_git=False)]
    assert [r["name"] for r in lh.commit_targets(rows, [0, 1, 2, 3, 4])] == ["a", "c"]
    assert lh.commit_targets(rows, []) == []


def test_select_all_dirty_checkbox(card, monkeypatch):
    card._populate([_row("a", uncommitted=2), _row("b"), _row("c", uncommitted=1)])
    card.sel_dirty.setChecked(True)
    assert card._selected_rows() == [0, 2]
    assert card.commit_btn.isEnabled() and "2 projects" in card.commit_btn.text()
    seen = []
    monkeypatch.setattr(card, "commit_projects", lambda infos: seen.append([i["name"] for i in infos]))
    card._commit_selected()
    assert seen == [["a", "c"]]
    card.table.selectRow(0)
    assert not card.sel_dirty.isChecked()
    card.sel_dirty.setChecked(True); card.sel_dirty.setChecked(False)
    assert card._selected_rows() == []


# --- Thresholds, largest folders, system caches --------------------------------

def test_settings_roundtrip_and_validation(tmp_path):
    f = tmp_path / "s.json"
    assert lh.load_settings(f) == {"env_idle_days": lh.ENV_IDLE_DAYS,
                                   "project_idle_days": lh.IDLE_DAYS}
    lh.save_settings({"env_idle_days": 3, "project_idle_days": 60}, f)
    assert lh.load_settings(f) == {"env_idle_days": 3, "project_idle_days": 60}
    f.write_text('{"env_idle_days": 0, "project_idle_days": "x"}')
    assert lh.load_settings(f)["env_idle_days"] == lh.ENV_IDLE_DAYS


def test_apply_settings_changes_eligibility(tmp_path, monkeypatch):
    monkeypatch.setattr(lh, "ENV_IDLE_DAYS", lh.ENV_IDLE_DAYS)
    monkeypatch.setattr(lh, "IDLE_DAYS", lh.IDLE_DAYS)
    lh.apply_settings({"env_idle_days": 2, "project_idle_days": 5})
    assert (lh.ENV_IDLE_DAYS, lh.IDLE_DAYS) == (2, 5)
    (tmp_path / "Makefile").write_text("")
    (tmp_path / "dist").mkdir()
    assert lh.classify_item(tmp_path, tmp_path / "dist", 1, 3)["eligible"] is False
    assert lh.classify_item(tmp_path, tmp_path / "dist", 1, 6)["eligible"] is True


def test_top_folders_ranks_and_skips_small(tmp_path):
    (tmp_path / "big").mkdir(); (tmp_path / "big" / "f").write_bytes(b"0" * 3_000_000)
    (tmp_path / "mid").mkdir(); (tmp_path / "mid" / "f").write_bytes(b"0" * 1_500_000)
    (tmp_path / "tiny").mkdir(); (tmp_path / "tiny" / "f").write_text("x")
    names = [p.name for _, p in lh.top_folders(tmp_path)]
    assert names == ["big", "mid"]


def test_system_cache_locations_only_existing(tmp_path):
    (tmp_path / ".npm" / "_cacache").mkdir(parents=True)
    (tmp_path / ".npm" / "_cacache" / "x").write_bytes(b"0" * 2048)
    found = lh.system_cache_locations(tmp_path)
    assert [f["label"] for f in found] == ["npm"] and found[0]["kb"] >= 2
    assert "npm cache clean" in found[0]["cmd"]


def test_clean_system_cache_empties_folder_when_tool_missing(tmp_path):
    cache = tmp_path / ".npm" / "_cacache"
    (cache / "sub").mkdir(parents=True)
    (cache / "sub" / "f").write_text("x"); (cache / "g").write_text("y")
    item = {"path": cache, "auto": True, "argv": ["definitely-not-a-tool-xyz"]}
    ok, msg = lh.clean_system_cache(item, home=tmp_path)
    assert ok and cache.is_dir() and list(cache.iterdir()) == []


def test_clean_system_cache_refuses_unsafe(tmp_path):
    outside = tmp_path / "out"; outside.mkdir(); (outside / "f").write_text("x")
    home = tmp_path / "home"; home.mkdir()
    assert not lh.clean_system_cache({"path": outside, "auto": True, "argv": None}, home)[0]
    assert (outside / "f").exists()
    inside = home / "c"; inside.mkdir(); (inside / "f").write_text("x")
    assert not lh.clean_system_cache({"path": inside, "auto": False, "argv": None}, home)[0]
    assert (inside / "f").exists()
    link = home / "l"; link.symlink_to(outside)
    assert not lh.clean_system_cache({"path": link, "auto": True, "argv": None}, home)[0]
    assert (outside / "f").exists()


def test_docker_is_report_only_and_risky_ones_unticked(tmp_path):
    for rel in ("Library/Containers/com.docker.docker", ".cache/huggingface", ".cache/uv"):
        (tmp_path / rel).mkdir(parents=True)
    by = {f["label"]: f for f in lh.system_cache_locations(tmp_path)}
    assert by["Docker data"]["auto"] is False
    assert by["Hugging Face models"]["default"] is False
    assert by["uv"]["default"] is True
