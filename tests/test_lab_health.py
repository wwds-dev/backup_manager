"""Lab Health helpers: manifest warning only where one is expected; safe commit."""
import subprocess
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
