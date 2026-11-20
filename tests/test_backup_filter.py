"""Folder "Back up now" and Excludes "Preview matches" keep secrets out of Google Drive
(readiness audit B1).

Every file here is a dummy: names like secrets, content "dummy". Nothing contacts
Google Drive; the only real rsync copies between two tmp_path folders.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import backup_filter  # noqa: E402
import main  # noqa: E402

SECRET_PATTERNS = """\
# File names that hold secrets.
.env
.env.*
.env-*
.env_*
*.env
*.env.*
.envrc
env.local
env.prod
env.production
env.dev
env.development
env.staging
env.test
.ENV
.ENV.*
*.ENV
"""

EXCLUDES = """\
# junk
.DS_Store
node_modules/
__pycache__/
/worktrees/
"""

# Same RSYNC_OPTS shape as _Admin/backup/backup_to_gdrive.sh.
SCRIPT = """\
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXCLUDES="$SCRIPT_DIR/gdrive_backup_excludes.txt"
RSYNC_OPTS=(
  -rltvh
  --update
  --modify-window=2
  --no-perms --no-owner --no-group
  --include='*.example' --include='*.sample' --include='*.template'   # before the .env excludes
  --exclude-from="$EXCLUDES"
  --exclude-from="$SCRIPT_DIR/secret_name_patterns.txt"   # secrets go to the Proton vault
  --stats
  --itemize-changes
)
"""

SECRETS = [".env", ".env.local", ".env.production", ".env-dev", ".env_old", "prod.env",
           "prod.env.bak", ".envrc", "env.local", "env.production", "sub/.env",
           "sub/deep/.env.local", "x.ENV"]
# No ".ENV": on case-insensitive APFS it is the same file as ".env".
KEPT = [".env.example", ".env.sample", ".env.template", "app.env.example", "config.template",
        "main.py", "sub/notes.md", "environment.md", "sub/deep/env.py"]
JUNK = [".DS_Store", "node_modules/pkg/index.js", "sub/__pycache__/m.pyc", "worktrees/a/f.txt"]


@pytest.fixture
def backup_dir(tmp_path):
    d = tmp_path / "backup"
    d.mkdir()
    (d / backup_filter.SECRETS_NAME).write_text(SECRET_PATTERNS)
    (d / backup_filter.EXCLUDES_NAME).write_text(EXCLUDES)
    (d / backup_filter.SCRIPT_NAME).write_text(SCRIPT)
    return d


@pytest.fixture
def tree(tmp_path):
    """~/Documents with one backed-up folder full of dummy files."""
    docs = tmp_path / "Documents"
    root = docs / "proj"
    for rel in SECRETS + KEPT + JUNK:
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("dummy")
    return docs


@pytest.fixture
def patched(monkeypatch, backup_dir, tree, tmp_path):
    dest = tmp_path / "Drive" / "Backups"
    monkeypatch.setattr(main, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(main, "DOCS", tree)
    monkeypatch.setattr(main, "DRIVE_ROOT", tmp_path / "Drive")
    monkeypatch.setattr(main, "DEST_ROOT", dest)
    (tmp_path / "Drive").mkdir()
    return SimpleNamespace(backup=backup_dir, docs=tree, dest=dest)


# --- the rsync argument list ------------------------------------------------
def test_single_folder_args_carry_the_secret_filter_in_rsync_order(patched):
    args = main.single_folder_rsync_args("proj")
    secrets = f"--exclude-from={patched.backup / 'secret_name_patterns.txt'}"
    junk = f"--exclude-from={patched.backup / 'gdrive_backup_excludes.txt'}"
    assert secrets in args and junk in args
    for keep in ("--include=*.example", "--include=*.sample", "--include=*.template"):
        # rsync is first-match: the includes must come before the .env excludes.
        assert args.index(keep) < args.index(junk) < args.index(secrets)
    assert args[-2:] == [f"{patched.docs / 'proj'}/", f"{patched.dest / 'proj'}/"]
    assert "--delete" not in args


class FakeProcess:
    """Stands in for QProcess: records what would have been run."""
    started: list = []

    class _Sig:
        def connect(self, *_):
            pass

    MergedChannels = object()

    def __init__(self, *_):
        self.readyReadStandardOutput = self._Sig()
        self.finished = self._Sig()

    def setProcessChannelMode(self, *_):
        pass

    def start(self, program, args):
        FakeProcess.started.append((program, list(args)))


class _Widget:
    def __init__(self):
        self.text = None

    def setText(self, t):
        self.text = t

    def setEnabled(self, *_):
        pass

    def clear(self):
        pass

    def insertPlainText(self, *_):
        pass


def _fake_card():
    return SimpleNamespace(proc=None, status_lbl=_Widget(), log=_Widget(), run_btn=_Widget(),
                           dry_btn=_Widget(), pause_btn=_Widget(), stop_btn=_Widget(),
                           _read_output=None, _finished=None,
                           runs_changed=SimpleNamespace(emit=lambda: None))


def test_run_single_folder_starts_rsync_with_the_shared_filter(patched, monkeypatch):
    FakeProcess.started = []
    monkeypatch.setattr(main, "QProcess", FakeProcess)
    main.BackupStatusCard.run_single_folder(_fake_card(), "proj")
    assert FakeProcess.started == [(main.RSYNC, main.single_folder_rsync_args("proj"))]


@pytest.mark.parametrize("break_it", ["missing", "empty", "script_drift", "no_script",
                                      "unknown_var"])
def test_run_single_folder_fails_closed(patched, monkeypatch, break_it):
    secrets = patched.backup / backup_filter.SECRETS_NAME
    script = patched.backup / backup_filter.SCRIPT_NAME
    if break_it == "missing":
        secrets.unlink()
    elif break_it == "empty":
        secrets.write_text("# only a comment\n\n")
    elif break_it == "script_drift":
        script.write_text(SCRIPT.replace(
            '  --exclude-from="$SCRIPT_DIR/secret_name_patterns.txt"', ""))
    elif break_it == "no_script":
        script.unlink()
    elif break_it == "unknown_var":
        script.write_text(SCRIPT.replace("$SCRIPT_DIR/secret", "$OTHER/secret"))
    with pytest.raises(backup_filter.FilterError):
        main.single_folder_rsync_args("proj")

    FakeProcess.started = []
    warned = []
    monkeypatch.setattr(main, "QProcess", FakeProcess)
    monkeypatch.setattr(main.QMessageBox, "warning", lambda *a, **k: warned.append(a))
    card = _fake_card()
    main.BackupStatusCard.run_single_folder(card, "proj")
    assert FakeProcess.started == []
    assert card.proc is None
    assert warned and "not started" in card.status_lbl.text


# --- what rsync really does with that list (local tmp copy only) -------------
def _rsync() -> str | None:
    return main.RSYNC if Path(main.RSYNC).exists() else shutil.which("rsync")


@pytest.mark.skipif(_rsync() is None, reason="no rsync on this machine")
def test_rsync_with_these_args_copies_no_secret(patched):
    args = main.single_folder_rsync_args("proj")
    dest = patched.dest / "proj"
    dest.mkdir(parents=True)
    r = subprocess.run([_rsync(), *args], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    copied = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()}
    assert not copied & set(SECRETS), copied & set(SECRETS)
    assert set(KEPT) <= copied
    assert not copied & set(JUNK)


# --- Preview matches uses the same rules ------------------------------------
def test_preview_lists_secrets_and_junk_but_not_examples(patched):
    rules = backup_filter.preview_rules(
        backup_filter.read_patterns(patched.backup / backup_filter.EXCLUDES_NAME),
        backup_filter.read_patterns(patched.backup / backup_filter.SECRETS_NAME))
    found = dict(backup_filter.excluded_paths(patched.docs / "proj", rules))
    for s in SECRETS:
        assert found.get(s) is True, s
    for k in KEPT:
        assert k not in found
    # An excluded folder is listed once and not walked into, as rsync does.
    assert found["node_modules/"] is False and "node_modules/pkg/index.js" not in found
    assert found["worktrees/"] is False
    assert found[".DS_Store"] is False


@pytest.mark.skipif(_rsync() is None, reason="no rsync on this machine")
def test_preview_agrees_with_rsync(patched):
    """Everything rsync left out is in the preview, and nothing it copied is."""
    dest = patched.dest / "proj"
    dest.mkdir(parents=True)
    subprocess.run([_rsync(), *main.single_folder_rsync_args("proj")],
                   capture_output=True, check=True, timeout=60)
    copied = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()}
    rules = backup_filter.preview_rules(
        backup_filter.read_patterns(patched.backup / backup_filter.EXCLUDES_NAME),
        backup_filter.read_patterns(patched.backup / backup_filter.SECRETS_NAME))
    excluded = [p.rstrip("/") for p, _ in backup_filter.excluded_paths(patched.docs / "proj", rules)]
    for rel in SECRETS + KEPT + JUNK:
        left_out = any(rel == e or rel.startswith(e + "/") for e in excluded)
        assert left_out == (rel not in copied), rel


def test_preview_dialog_shows_secrets(patched, monkeypatch, qapp):
    monkeypatch.setattr(main, "read_folders", lambda: ["proj"])
    shown = {}

    def fake_exec(dlg):
        from PySide6.QtWidgets import QPlainTextEdit
        shown["text"] = dlg.findChild(QPlainTextEdit).toPlainText()
        return 0

    monkeypatch.setattr(main.QDialog, "exec", fake_exec)
    d = main.ExcludesDialog()
    d.edit.setPlainText(EXCLUDES)
    d.preview_matches()
    lines = shown["text"].splitlines()
    assert "proj/.env  [secret: never sent to Google Drive]" in lines
    assert not any(l.startswith("proj/.env.example") for l in lines)
    d.deleteLater()


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# --- the two paths cannot drift ---------------------------------------------
def test_fixture_script_parses_to_the_expected_filter(backup_dir):
    assert backup_filter.script_filter_args(backup_dir / "backup_to_gdrive.sh", backup_dir) \
        == backup_filter.expected_filter_args(backup_dir)


@pytest.mark.skipif(not (main.BACKUP_DIR / backup_filter.SCRIPT_NAME).exists(),
                    reason="the lab's _Admin/backup scripts are not on this machine")
def test_live_backup_script_filters_like_the_app():
    """Fails if backup_to_gdrive.sh's include/exclude filter changes without this app.
    Reads the script and the pattern files' names only; runs nothing."""
    assert backup_filter.rsync_filter_args(main.BACKUP_DIR) \
        == backup_filter.expected_filter_args(main.BACKUP_DIR)
    live = backup_filter.read_patterns(main.BACKUP_DIR / backup_filter.SECRETS_NAME)
    assert set(backup_filter.read_patterns_text(SECRET_PATTERNS)) <= set(live)
