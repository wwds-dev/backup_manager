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
    assert set(r1) == {"rule", "path", "rel", "size", "age_days", "why"}
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
        opened.append((str(file), mode))
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
    assert opened and all(set(m) <= set("rbt") and "+" not in m and "w" not in m and "a" not in m and "x" not in m
                          for _, m in opened)
    assert {os.path.basename(p) for p, _ in opened} <= {"AGENTS.md", "README.md"}
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    assert not [p for p, fl in fd_opened if fl & write_flags]


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
    assert by_rule(lrc.scan(clean, now=NOW)) == {"R1": ["secret_name"]}


def test_broken_link_is_listed_with_its_target_and_not_followed(clean, outside, monkeypatch):
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
