"""Lab root checks R1-R6: one finding per rule, none for a clean lab, read only, symlinks never followed."""
import builtins
import io
import os
import socket
import subprocess
import time

import pytest

import lab_root_checks as lrc

NOW = time.time()


def write(p, text="x", age_days=None):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    if age_days is not None:
        t = NOW - age_days * 86400
        os.utime(p, (t, t))
    return p


def by_rule(findings):
    out = {}
    for f in findings:
        out.setdefault(f["rule"], []).append(f["rel"])
    return out


DOCS = "`AGENTS.md` `README.md` `docs/` `old.bak` `lab_notes.json` `ok_link` `proj_ok`\n"


@pytest.fixture
def clean(tmp_path):
    """A lab with nothing to report."""
    root = tmp_path / "lab"
    write(root / "AGENTS.md", DOCS)
    write(root / "README.md", "readme\n")
    write(root / "CLAUDE.md", "@AGENTS.md\n")
    write(root / "docs" / "a.md")
    write(root / "active" / "proj_ok" / "f.txt")
    write(root / "lab_notes.json", "{}")
    write(root / ".hidden_file")
    write(root / ".cache" / "c")
    write(root / ".DS_Store")
    os.symlink("docs/a.md", root / "ok_link")        # resolves, named in the docs
    return root


@pytest.fixture
def dirty(clean):
    """The clean lab plus exactly one thing for each rule."""
    write(clean / "stray.txt", "x" * 10, age_days=3)                    # R1
    write(clean / "old.bak", "y", age_days=40)                          # R2 (named, so not R1)
    write(clean / "_to_delete" / "a.txt", "zz", age_days=20)            # R3
    (clean / "empty_dir").mkdir()                                       # R4
    write(clean / "active" / "undocumented" / "f")                      # R5
    os.symlink("nowhere/target", clean / "dead_link")                   # R6
    return clean


def test_clean_lab_has_no_findings(clean):
    assert lrc.scan(clean, now=NOW) == []


def test_one_finding_per_rule(dirty):
    got = by_rule(lrc.scan(dirty, now=NOW))
    assert got == {"R1": ["stray.txt"], "R2": ["old.bak"], "R3": ["_to_delete"], "R4": ["empty_dir"],
                   "R5": ["active/undocumented"], "R6": ["dead_link"]}


def test_finding_fields(dirty):
    f = {x["rule"]: x for x in lrc.scan(dirty, now=NOW)}
    r1 = f["R1"]
    assert set(r1) == {"rule", "path", "rel", "size", "age_days", "partial", "why"}   # "partial" added by the fix pass
    assert r1["path"] == str(dirty / "stray.txt") and r1["size"] == 10 and r1["age_days"] == 3
    assert f["R2"]["age_days"] == 40 and f["R2"]["size"] == 1
    assert f["R3"]["age_days"] == 20 and f["R3"]["size"] == 2 and "1 file(s)" in f["R3"]["why"]
    assert all(x["why"] and "\n" not in x["why"] for x in f.values())


def test_findings_are_json_ready_and_ordered(dirty):
    import json
    found = lrc.scan(dirty, now=NOW)
    json.dumps(found)
    assert [f["rule"] for f in found] == sorted(f["rule"] for f in found)


def test_dotfiles_and_always_ok_names_are_not_unexpected(clean):
    write(clean / ".something_new")
    write(clean / ".newdir" / "f")
    (clean / ".newdir_empty").mkdir()
    assert lrc.scan(clean, now=NOW) == []


def test_named_in_readme_counts_as_known(clean):
    write(clean / "only_in_readme.py")
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R1": ["only_in_readme.py"]}
    write(clean / "README.md", "see `only_in_readme.py` here\n")
    assert lrc.scan(clean, now=NOW) == []


def test_path_segments_in_docs_are_known(clean):
    write(clean / "scripts" / "a.sh")
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R1": ["scripts"]}
    write(clean / "AGENTS.md", DOCS + "`scripts/a.sh`\n")
    assert lrc.scan(clean, now=NOW) == []


def test_r1_folder_with_content_is_flagged_with_its_size(clean):
    write(clean / "stuff" / "a", "x" * 100)
    write(clean / "stuff" / "sub" / "b", "y" * 50)
    [f] = lrc.scan(clean, now=NOW)
    assert f["rule"] == "R1" and f["size"] == 150 and "folder" in f["why"]


def test_r1_does_not_double_report_an_empty_folder_or_broken_link(clean):
    (clean / "empty_dir").mkdir()
    os.symlink("nowhere", clean / "dead_link")
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R4": ["empty_dir"], "R6": ["dead_link"]}


def test_r2_patterns(clean):
    names = ["a.orig", "b~", "c.tmp", "patch_x.py", "fix_y.py", "_patch1.py", "d.bak_1"]
    for n in names:
        write(clean / n)
    write(clean / "AGENTS.md", DOCS + " ".join(f"`{n}`" for n in names))     # named, so not R1
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R2": sorted(names)}


def test_r2_ignores_normal_names_and_folders(clean):
    write(clean / "AGENTS.md", DOCS + "`notes.py` `backup.d`")
    write(clean / "notes.py")
    write(clean / "backup.d" / "x")
    (clean / "dir.bak").mkdir()
    write(clean / "dir.bak" / "f")
    got = by_rule(lrc.scan(clean, now=NOW))
    assert "R2" not in got and got == {"R1": ["dir.bak"]}


def test_r3_absent_and_present(clean):
    assert "R3" not in by_rule(lrc.scan(clean, now=NOW))
    write(clean / "_to_delete" / "a" / "b", "q" * 7, age_days=9)
    write(clean / "_to_delete" / "c", "q", age_days=2)
    [f] = lrc.scan(clean, now=NOW)
    assert f["rule"] == "R3" and f["size"] == 8 and f["age_days"] == 9 and "2 file(s)" in f["why"]


def test_r4_only_top_level_and_not_active_or_dot_or_disposable(clean):
    (clean / "active" / "proj_ok" / "empty_inside").mkdir()
    (clean / "docs" / "empty_inside").mkdir()
    (clean / "node_modules").mkdir()
    (clean / "__pycache__").mkdir()
    (clean / ".emptydot").mkdir()
    write(clean / "AGENTS.md", DOCS + "`node_modules` `__pycache__`")
    assert lrc.scan(clean, now=NOW) == []
    (clean / "e1").mkdir()
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R4": ["e1"]}


def test_r4_named_empty_folder_is_still_empty(clean):
    (clean / "backups").mkdir()
    write(clean / "AGENTS.md", DOCS + "`backups/`")
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R4": ["backups"]}


def test_r5_named_project_and_dot_entries_are_fine(clean):
    write(clean / "active" / ".hidden_proj" / "f")
    write(clean / "active" / "stray_file.txt")          # a file in active/ is not a project
    assert lrc.scan(clean, now=NOW) == []
    write(clean / "active" / "proj_two" / "f")
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R5": ["active/proj_two"]}


def test_r5_is_the_folder_audit_match_a_backtick_then_the_name(clean):
    # "prefix match, as in Folder Audit": the name only has to follow a backtick (not "an exact match")
    write(clean / "active" / "proj_two" / "f")
    write(clean / "AGENTS.md", DOCS + "see proj_two and active/proj_two/ in prose")      # not a `proj_two span
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R5": ["active/proj_two"]}
    write(clean / "AGENTS.md", DOCS + "`proj_two`")
    assert lrc.scan(clean, now=NOW) == []


def test_r6_resolving_link_is_fine_and_broken_ones_are_found_at_root_and_active(clean):
    os.symlink("../docs/a.md", clean / "active" / "proj_ok_link")
    write(clean / "AGENTS.md", DOCS + "`proj_ok_link`")
    assert lrc.scan(clean, now=NOW) == []
    os.symlink("gone", clean / "dead1")
    os.symlink("gone", clean / "active" / "dead2")
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R6": ["active/dead2", "dead1"]}


def test_r6_symlink_loop_is_broken(clean):
    os.symlink("loop2", clean / "loop1")
    os.symlink("loop1", clean / "loop2")
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R6": ["loop1", "loop2"]}


def test_missing_lab_or_no_active_is_empty_not_an_error(tmp_path):
    assert lrc.scan(tmp_path / "nope", now=NOW) == []
    (tmp_path / "bare").mkdir()
    assert lrc.scan(tmp_path / "bare", now=NOW) == []


def test_walk_cap_makes_size_unknown(clean, monkeypatch):
    for i in range(5):
        write(clean / "big" / f"f{i}")
    monkeypatch.setattr(lrc, "_WALK_CAP", 3)
    [f] = lrc.scan(clean, now=NOW)
    assert f["rule"] == "R1" and f["size"] is None


# ---- read only -------------------------------------------------------------------------------

def _tree(root):
    return sorted((str(p), p.lstat().st_mtime_ns, p.lstat().st_size) for p in root.rglob("*"))


def test_opens_nothing_for_writing_runs_no_subprocess_no_network(dirty, monkeypatch):
    opened, fd_opened = [], []
    real_open, real_os_open = builtins.open, os.open

    def spy_open(file, mode="r", *a, **k):
        opened.append((file, mode))
        return real_open(file, mode, *a, **k)

    def spy_os_open(path, flags, *a, **k):
        fd_opened.append((str(path), flags))
        return real_os_open(path, flags, *a, **k)

    def boom(*a, **k):
        pytest.fail("the scan must not do this")

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(io, "open", spy_open)
    monkeypatch.setattr(os, "open", spy_os_open)
    for mod, names in ((subprocess, ("run", "Popen", "call", "check_call", "check_output")),
                       (os, ("system", "popen", "remove", "unlink", "rename", "replace", "rmdir", "mkdir",
                             "makedirs", "symlink", "link", "utime", "chmod", "truncate", "write")),
                       (socket, ("socket", "create_connection", "getaddrinfo"))):
        for n in names:
            monkeypatch.setattr(mod, n, boom)
    import shutil
    monkeypatch.setattr(shutil, "rmtree", boom)
    monkeypatch.setattr(shutil, "move", boom)

    before = _tree(dirty)
    assert lrc.scan(dirty, now=NOW)
    assert _tree(dirty) == before
    # the docs are opened with os.open (O_NOFOLLOW | O_NONBLOCK) and wrapped with fdopen, which reaches
    # io.open with the descriptor: a descriptor is not a path, so only the os.open paths name files
    assert opened and all(isinstance(f, int) for f, _ in opened)
    assert all(set(m) <= set("rbt") and "+" not in m and "w" not in m and "a" not in m and "x" not in m
               for _, m in opened)
    assert {os.path.basename(p) for p, _ in fd_opened} == {"AGENTS.md", "README.md"}
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    assert not [p for p, fl in fd_opened if fl & write_flags]
    assert all(fl & os.O_NOFOLLOW and fl & os.O_NONBLOCK for _, fl in fd_opened)


# ---- symlinks are listed, never followed -------------------------------------------------------

@pytest.fixture
def outside(tmp_path):
    out = tmp_path / "outside"
    write(out / "big" / "a", "A" * 5000)
    write(out / "big" / "b", "B" * 5000)
    (out / "empty").mkdir()
    write(out / "stale.bak", "s")
    write(out / "docs.md", "`secret_name`")
    return out


def test_symlinks_out_of_the_lab_are_listed_but_not_followed(clean, outside, monkeypatch):
    os.symlink(outside / "big", clean / "outlink")              # R1: unexpected, size is the link's own
    os.symlink(outside / "empty", clean / "emptylink")          # not R4: a link is not a folder
    os.symlink(outside / "stale.bak", clean / "stale_link.bak")  # not R2: a link is not a file
    os.symlink(outside / "big", clean / "_to_delete")           # R3: listed, never walked
    os.symlink(outside / "big", clean / "active" / "proj_link")  # R5: undocumented

    touched = []
    for mod, names in ((os, ("scandir", "listdir", "walk")),):
        for n in names:
            real = getattr(mod, n)

            def spy(path=".", *a, _real=real, **k):
                touched.append(str(path))
                return _real(path, *a, **k)
            monkeypatch.setattr(mod, n, spy)
    real_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda f, *a, **k: touched.append(str(f)) or real_open(f, *a, **k))

    got = {f["rel"]: f for f in lrc.scan(clean, now=NOW)}
    assert not [t for t in touched if str(outside) in t]
    assert set(by_rule(got.values())) == {"R1", "R3", "R5"}
    assert by_rule(got.values())["R1"] == ["emptylink", "outlink", "stale_link.bak"]
    assert got["outlink"]["size"] == os.lstat(clean / "outlink").st_size < 1000     # not the 10000 inside
    assert got["_to_delete"]["rule"] == "R3" and got["_to_delete"]["size"] < 1000
    assert got["active/proj_link"]["rule"] == "R5" and "symlink" in got["active/proj_link"]["why"]


def test_readme_symlink_out_of_the_lab_is_not_read(clean, outside):
    os.remove(clean / "README.md")
    os.symlink(outside / "docs.md", clean / "README.md")        # names `secret_name`
    write(clean / "secret_name")
    # not read, so `secret_name` is not honoured; the symlinked doc is one visible NOTE row and R1 and R5
    # are not checked (before the fix pass: one R1 row for secret_name)
    found = lrc.scan(clean, now=NOW)
    assert by_rule(found) == {"NOTE": ["README.md"]}
    assert "not read" in found[0]["why"] and "R1 and R5 were not checked" in found[0]["why"]


def test_broken_link_is_listed_with_its_target_and_not_followed(clean, outside, monkeypatch):
    # a target is only checked when it is under the lab or HOME (secure P3-2), so HOME is the folder above both
    monkeypatch.setenv("HOME", str(outside.parent))
    os.symlink(outside / "missing_dir", clean / "dead_link")
    seen = []
    real = os.scandir
    monkeypatch.setattr(os, "scandir", lambda p=".": seen.append(str(p)) or real(p))
    [f] = lrc.scan(clean, now=NOW)
    assert f["rule"] == "R6" and str(outside / "missing_dir") in f["why"] and not [s for s in seen if "outside" in s]


def test_links_inside_a_measured_folder_are_not_descended(clean, outside):
    write(clean / "stuff" / "a", "x" * 10)
    os.symlink(outside / "big", clean / "stuff" / "link_out")
    [f] = lrc.scan(clean, now=NOW)
    assert f["rule"] == "R1" and f["size"] < 1000


# ---- fix pass after the review and the security review (docs/audit/lab-root-checks-*.md) ------------

@pytest.fixture
def home(tmp_path, monkeypatch):
    """A HOME that is neither the lab nor the folder holding `outside`."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    return h


def test_r5_is_a_prefix_match_so_a_longer_name_hides_a_missing_project(clean):
    # documents Folder Audit's behaviour, kept on purpose (review P3-1): `proj_okx` also names proj_ok
    write(clean / "active" / "proj_ok2" / "f")
    write(clean / "AGENTS.md", DOCS + "`proj_ok2x`")
    assert lrc.scan(clean, now=NOW) == []
    write(clean / "AGENTS.md", DOCS + "`xproj_ok2`")                 # the name must follow the backtick
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R5": ["active/proj_ok2"]}


# -- R3 and R4 and R6 on `_to_delete` (review P3-2) --

def test_empty_to_delete_is_reported_once_as_r3(clean):
    (clean / "_to_delete").mkdir()
    [f] = lrc.scan(clean, now=NOW)
    assert f["rule"] == "R3" and "0 file(s)" in f["why"]


def test_broken_link_named_to_delete_is_r6_only(clean):
    os.symlink("nowhere", clean / "_to_delete")
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R6": ["_to_delete"]}


def test_to_delete_as_a_file_or_a_link_to_a_folder_is_worded_for_what_it_is(clean):
    write(clean / "_to_delete", "x")
    [f] = lrc.scan(clean, now=NOW)
    assert f["rule"] == "R3" and "as a file, not a folder" in f["why"]
    os.remove(clean / "_to_delete")
    os.symlink("docs", clean / "_to_delete")
    [f] = lrc.scan(clean, now=NOW)
    assert f["rule"] == "R3" and "as a symlink" in f["why"] and "not a folder" not in f["why"]


# -- Unicode (review P3-3 and P3-11) --

@pytest.mark.parametrize("disk,doc", [("Caf\u00e9", "Cafe\u0301"), ("Cafe\u0301", "Caf\u00e9")])
def test_r1_and_r5_compare_names_as_nfc(clean, disk, doc):
    write(clean / disk, "x")
    write(clean / "active" / disk / "f")
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R1": [disk], "R5": [f"active/{disk}"]}
    write(clean / "AGENTS.md", DOCS + f"`{doc}`")
    assert lrc.scan(clean, now=NOW) == []


def test_non_ascii_names_are_reported_and_json_ready(clean):
    import json
    write(clean / "\u00fcber \u2603.txt", "x")
    [f] = lrc.scan(clean, now=NOW)
    assert f["rel"] == "\u00fcber \u2603.txt"
    json.dumps([f])


# -- a doc that is not read (review P3-4) --

def test_symlinked_agents_md_is_one_note_row_and_r1_r5_are_off(clean, outside):
    os.remove(clean / "AGENTS.md")
    os.symlink(outside / "docs.md", clean / "AGENTS.md")
    write(clean / "stray.txt")
    write(clean / "active" / "undocumented" / "f")
    (clean / "empty_dir").mkdir()
    found = lrc.scan(clean, now=NOW)
    assert by_rule(found) == {"NOTE": ["AGENTS.md"], "R4": ["empty_dir"]}
    assert "AGENTS.md" in found[-1]["why"] and "R1 and R5 were not checked" in found[-1]["why"]


def test_dangling_or_fifo_doc_is_a_note_and_does_not_block(clean):
    os.remove(clean / "README.md")
    os.mkfifo(clean / "README.md")                      # opening it for read would block without O_NONBLOCK
    assert by_rule(lrc.scan(clean, now=NOW)) == {"NOTE": ["README.md"]}
    os.remove(clean / "README.md")
    os.symlink("gone", clean / "README.md")             # also a broken link at the root: R6 says so, NOTE says it was not read
    assert by_rule(lrc.scan(clean, now=NOW)) == {"NOTE": ["README.md"], "R6": ["README.md"]}
    os.remove(clean / "README.md")                       # a missing doc is not a NOTE: as before
    assert lrc.scan(clean, now=NOW) == []


def test_read_doc_states(tmp_path, outside):
    f = write(tmp_path / "d.md", "hello")
    assert lrc._read_doc(f) == "hello"
    assert lrc._read_doc(tmp_path / "missing.md") == ""
    os.symlink(f, tmp_path / "ln.md")
    assert lrc._read_doc(tmp_path / "ln.md") is None
    os.mkfifo(tmp_path / "fifo.md")
    assert lrc._read_doc(tmp_path / "fifo.md") is None
    os.chmod(f, 0)
    try:
        if os.geteuid() != 0:
            assert lrc._read_doc(f) is None
    finally:
        os.chmod(f, 0o644)


def test_read_doc_does_not_leak_a_descriptor(clean, monkeypatch):
    opened, closed = [], []
    real_open, real_close = os.open, os.close
    monkeypatch.setattr(os, "open", lambda *a, **k: opened.append(real_open(*a, **k)) or opened[-1])
    monkeypatch.setattr(os, "close", lambda fd: closed.append(fd) or real_close(fd))
    os.remove(clean / "README.md")
    os.mkfifo(clean / "README.md")                      # opened, found not regular, closed
    lrc.scan(clean, now=NOW)
    assert opened
    for fd in opened:                                      # every descriptor is closed again, by us or by fdopen's `with`
        with pytest.raises(OSError):
            os.fstat(fd)


# -- a failing scan (review P3-5, security P3-7) --

def test_scan_safe_turns_an_exception_into_one_note_row(clean, monkeypatch):
    monkeypatch.setattr(lrc, "scan", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom with /secret/path")))
    [f] = lrc.scan_safe(clean, now=NOW)
    assert f["rule"] == "NOTE" and f["path"] == str(clean) and f["size"] is None and f["age_days"] is None
    assert "failed" in f["why"] and "ValueError" in f["why"] and "secret" not in f["why"]


def test_scan_safe_is_scan_when_nothing_fails(dirty):
    assert lrc.scan_safe(dirty, now=NOW) == lrc.scan(dirty, now=NOW)


# -- sizes that are not known (review P3-6, security P3-3) --

def test_a_complete_measure_is_not_partial(dirty):
    assert {f["rule"]: f["partial"] for f in lrc.scan(dirty, now=NOW)} == {
        "R1": False, "R2": False, "R3": False, "R4": False, "R5": False, "R6": False}


def test_cap_is_partial_with_unknown_size_and_r3_text_has_no_count_or_age(clean, monkeypatch):
    for i in range(5):
        write(clean / "_to_delete" / f"f{i}", age_days=50)
    monkeypatch.setattr(lrc, "_WALK_CAP", 3)
    [f] = lrc.scan(clean, now=NOW)
    assert f["rule"] == "R3" and f["size"] is None and f["partial"] is True
    assert "not measured" in f["why"] and "file(s)" not in f["why"] and "days old" not in f["why"]
    assert f["age_days"] == 0                           # the folder's own age (just made), not a guess from a partial walk


@pytest.mark.parametrize("cap,known", [(5, True), (4, False)])
def test_cap_boundary_exactly_at_the_cap_is_measured(clean, monkeypatch, cap, known):
    for i in range(5):
        write(clean / "big" / f"f{i}", "xy")             # 5 entries inside
    monkeypatch.setattr(lrc, "_WALK_CAP", cap)
    [f] = lrc.scan(clean, now=NOW)
    assert (f["size"] == 10) is known and (f["size"] is None) is (not known) and f["partial"] is (not known)


def test_cap_counts_entries_across_nested_folders(clean, monkeypatch):
    write(clean / "big" / "a" / "f1")
    write(clean / "big" / "a" / "b" / "f2")
    write(clean / "big" / "c" / "f3")                    # 6 entries: a, a/f1, a/b, a/b/f2, c, c/f3
    monkeypatch.setattr(lrc, "_WALK_CAP", 5)
    [f] = lrc.scan(clean, now=NOW)
    assert f["size"] is None and f["partial"]
    monkeypatch.setattr(lrc, "_WALK_CAP", 6)
    [f] = lrc.scan(clean, now=NOW)
    assert f["size"] == 3 and not f["partial"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read a mode-000 folder")
def test_unreadable_subfolder_gives_a_lower_bound_and_partial(clean):
    write(clean / "_to_delete" / "ok", "abcd", age_days=5)
    write(clean / "_to_delete" / "locked" / "hidden", "z" * 100)
    os.chmod(clean / "_to_delete" / "locked", 0)
    try:
        [f] = lrc.scan(clean, now=NOW)
    finally:
        os.chmod(clean / "_to_delete" / "locked", 0o755)
    assert f["size"] == 4 and f["partial"] is True       # not "0 B" and not complete
    assert "at least 1 file(s) seen" in f["why"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read a mode-000 folder")
def test_unreadable_top_is_unknown_not_zero(clean):
    write(clean / "locked" / "hidden", "z" * 100)
    os.chmod(clean / "locked", 0)
    try:
        [f] = lrc.scan(clean, now=NOW)
    finally:
        os.chmod(clean / "locked", 0o755)
    assert f["rule"] == "R1" and f["size"] is None and f["partial"] is True


def test_a_file_that_vanishes_during_the_walk_makes_the_size_partial(clean, monkeypatch):
    write(clean / "stuff" / "a", "xxxx")
    write(clean / "stuff" / "gone", "yyyyyy")
    real = lrc._lstat
    monkeypatch.setattr(lrc, "_lstat", lambda p: None if str(p).endswith("gone") else real(p))
    [f] = lrc.scan(clean, now=NOW)
    assert f["size"] == 4 and f["partial"] is True


# -- an entry that vanishes (review P3-7) --

def test_a_vanished_entry_has_no_size_and_no_age(clean, monkeypatch):
    write(clean / "stray.txt", "x")
    real = lrc._lstat
    monkeypatch.setattr(lrc, "_lstat", lambda p: None if str(p).endswith("stray.txt") else real(p))
    [f] = lrc.scan(clean, now=NOW)
    assert f["rule"] == "R1" and f["size"] is None and f["age_days"] is None and f["partial"] is True


# -- R5 rows are not measured (review P3-8) --

def test_r5_rows_are_not_measured_but_are_aged(clean, monkeypatch):
    write(clean / "active" / "undocumented" / ".venv" / "big", "x" * 1000)
    os.utime(clean / "active" / "undocumented", (NOW - 9 * 86400, NOW - 9 * 86400))
    walked = []
    real = os.walk
    monkeypatch.setattr(os, "walk", lambda p, *a, **k: walked.append(str(p)) or real(p, *a, **k))
    [f] = lrc.scan(clean, now=NOW)
    assert f["rule"] == "R5" and f["size"] is None and f["age_days"] == 9 and f["partial"] is False
    assert not [w for w in walked if "undocumented" in w]


# -- a symlinked active/ is not followed (review P3-9) --

def test_symlinked_active_is_not_followed(clean, outside, monkeypatch):
    shutil_rm(clean / "active")
    os.symlink(outside / "big", clean / "active")
    os.symlink("gone", outside / "big" / "dead")
    seen = []
    real = os.scandir
    monkeypatch.setattr(os, "scandir", lambda p=".": seen.append(str(p)) or real(p))
    assert by_rule(lrc.scan(clean, now=NOW)) == {"NOTE": ["active"]}   # leads out: not checked, and nothing under it is read
    assert not [s for s in seen if "outside" in s or s.endswith("active")]


def shutil_rm(p):
    import shutil
    shutil.rmtree(p)


# -- age (review P3-11) --

def test_age_rounds_down_and_a_future_mtime_is_zero(clean):
    write(clean / "a.txt", "x", age_days=1.99)
    write(clean / "b.txt", "x", age_days=2)
    write(clean / "c.txt", "x", age_days=-5)             # modified in the future
    got = {f["rel"]: f["age_days"] for f in lrc.scan(clean, now=NOW)}
    assert got == {"a.txt": 1, "b.txt": 2, "c.txt": 0}


# -- R2 on a dotfile (review P3-11) --

def test_r2_flags_a_stale_dotfile_although_r1_skips_dotfiles(clean):
    write(clean / ".hid.bak", "x")
    write(clean / ".hid.txt", "x")
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R2": [".hid.bak"]}


# -- _measure and symlinks as the top (security P3-1) --

def test_measure_refuses_a_symlink_as_the_top_and_does_not_walk_it(tmp_path, outside, monkeypatch):
    os.symlink(outside / "big", tmp_path / "ln")
    walked = []
    real = os.walk
    monkeypatch.setattr(os, "walk", lambda p, *a, **k: walked.append(p) or real(p, *a, **k))
    assert lrc._measure(str(tmp_path / "ln")) == (None, 0, None, True)
    assert lrc._measure(str(tmp_path / "missing")) == (None, 0, None, True)
    assert walked == []


# -- links that lead out of the lab and HOME are not stat'ed (security P3-2) --

def test_link_out_of_lab_and_home_is_a_note_never_r6_and_is_not_touched(clean, outside, home, monkeypatch):
    os.symlink(outside / "missing", clean / "far_link")            # would be broken, but it is not checked
    os.symlink(outside / "big", clean / "far_dir")                 # a real folder out there
    write(clean / "AGENTS.md", DOCS + "`far_link` `far_dir`")
    touched = []
    for name in ("stat", "lstat", "scandir", "listdir"):
        real = getattr(os, name)

        def spy(p=".", *a, _real=real, **k):
            touched.append(str(p))
            return _real(p, *a, **k)
        monkeypatch.setattr(os, name, spy)
    found = lrc.scan(clean, now=NOW)
    assert by_rule(found) == {"NOTE": ["far_dir", "far_link"]}
    assert all("not checked" in f["why"] and str(outside) in f["why"] for f in found)
    assert not [t for t in touched if str(outside) in t]


def test_a_hop_through_an_in_lab_link_to_outside_is_not_followed(clean, outside, home, monkeypatch):
    os.symlink(outside / "big", clean / "hop")                     # in the lab, leads out
    os.symlink("hop/a", clean / "via_hop")                         # lexically inside the lab, passes through `hop`
    write(clean / "AGENTS.md", DOCS + "`hop` `via_hop`")
    touched = []
    real = os.lstat
    monkeypatch.setattr(os, "lstat", lambda p, *a, **k: touched.append(str(p)) or real(p, *a, **k))
    found = lrc.scan(clean, now=NOW)
    assert by_rule(found) == {"NOTE": ["hop", "via_hop"]}
    assert not [t for t in touched if str(outside) in t]


def test_link_under_home_is_checked_and_broken_ones_are_r6(clean, outside, home):
    write(home / "notes" / "n.txt")
    os.symlink(home / "notes" / "n.txt", clean / "ok_home")
    os.symlink(home / "notes" / "missing", clean / "dead_home")
    write(clean / "AGENTS.md", DOCS + "`ok_home`")
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R6": ["dead_home"]}


def test_chain_of_in_lab_links_resolves_and_a_long_chain_is_broken(clean):
    os.symlink("docs/a.md", clean / "l1")
    os.symlink("l1", clean / "l2")
    os.symlink("l2", clean / "l3")
    write(clean / "AGENTS.md", DOCS + "`l1` `l2` `l3`")
    assert lrc.scan(clean, now=NOW) == []
    os.symlink("..", clean / "docs" / "up")                        # a link through `..`
    os.symlink("docs/up/docs/a.md", clean / "via_up")
    write(clean / "AGENTS.md", DOCS + "`l1` `l2` `l3` `via_up`")
    assert lrc.scan(clean, now=NOW) == []
    os.symlink("docs/a.md/inside", clean / "through_file")         # a file used as a folder
    for i in range(45):                                            # longer than the hop limit: broken, as the OS would say
        os.symlink(f"c{i + 1}", clean / "docs" / f"c{i}")
    os.symlink("a.md", clean / "docs" / "c45")
    os.symlink("docs/c0", clean / "long_chain")
    write(clean / "AGENTS.md", DOCS + "`l1` `l2` `l3` `via_up` `through_file` `long_chain`")
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R6": ["long_chain", "through_file"]}


def test_a_link_already_listed_gets_no_extra_note(clean, outside, home):
    os.symlink(outside / "big", clean / "far")                     # unnamed: R1 lists it
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R1": ["far"]}
