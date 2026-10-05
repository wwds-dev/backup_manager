"""Starting at login must come up in the menu bar, not in front.

"Open at login" used to be a System Events login item pointing at the bundle.
A login item cannot pass arguments, so the app started the only way it knows
without them: a window in the foreground and a dock tile, at every login. The
app already had a --background mode; it just had no way to ask for it.

So the setting is a LaunchAgent now (the same shape as Lab Hub's
com.netrunner3000.labhub.login), and these tests pin the two parts that make it
quiet: --background in the arguments, and no leftover login item racing it.
"""

from __future__ import annotations

import plistlib

import pytest

import main


@pytest.fixture
def agent(tmp_path, monkeypatch):
    plist = tmp_path / "LaunchAgents" / f"{main.LOGIN_AGENT_LABEL}.plist"
    monkeypatch.setattr(main, "LOGIN_AGENT_PLIST", plist)
    monkeypatch.setattr(main, "APP_BUNDLE", tmp_path / "Backup Control Center.app")
    (tmp_path / "Backup Control Center.app").mkdir()
    calls = []
    monkeypatch.setattr(main, "run_cmd",
                        lambda cmd, **kw: (calls.append(cmd), (0, "", ""))[1])
    monkeypatch.setattr(main, "_legacy_login_item", lambda: False)
    return plist, calls


def test_enabling_writes_a_background_launch_agent(agent):
    plist, calls = agent
    ok, err = main.set_login_item(True)
    assert ok, err

    spec = plistlib.loads(plist.read_bytes())
    assert spec["Label"] == main.LOGIN_AGENT_LABEL
    assert spec["RunAtLoad"] is True
    # The whole point: without --background the app opens a window and takes
    # the dock at login.
    assert "--background" in spec["ProgramArguments"]
    assert spec["ProgramArguments"][0] == "/usr/bin/open"
    assert any("launchctl" in c[0] and "load" in c for c in calls)


def test_disabling_removes_the_agent(agent):
    plist, _ = agent
    main.set_login_item(True)
    assert plist.exists()
    ok, err = main.set_login_item(False)
    assert ok, err
    assert not plist.exists()
    assert main.is_login_item() is False


def test_enabling_clears_the_old_login_item(agent, monkeypatch):
    """Both would fire, and the login item is the one that opens a window."""
    removed = []
    monkeypatch.setattr(main, "_remove_legacy_login_item",
                        lambda: removed.append(True))
    main.set_login_item(True)
    assert removed == [True]


def test_enabling_without_the_bundle_reports_why(agent, monkeypatch):
    plist, _ = agent
    monkeypatch.setattr(main, "APP_BUNDLE", plist.parent / "missing.app")
    ok, err = main.set_login_item(True)
    assert not ok
    assert "not installed" in err
    assert not plist.exists()


def test_migration_converts_an_existing_login_item(agent, monkeypatch):
    plist, _ = agent
    monkeypatch.setattr(main, "_legacy_login_item", lambda: True)
    main.migrate_login_item()
    assert plist.exists()
    assert "--background" in plistlib.loads(plist.read_bytes())["ProgramArguments"]


def test_migration_leaves_an_opted_out_user_alone(agent, monkeypatch):
    plist, _ = agent
    monkeypatch.setattr(main, "_legacy_login_item", lambda: False)
    main.migrate_login_item()
    assert not plist.exists()
