"""Shared fixtures. No test may touch the live ~/Library/Application Support/Backup Control Center
files: the secrets paths (cloud_quota) and the paths main.py derives from them at import time
(state.json, quota_history.json, gui.lock, workspace_report.json, show_request; icloud_du.log is built from SECRETS_DIR at call time).

Two layers: a session-wide baseline, so that when a per-test patch is undone the path falls back
to a scratch folder and never to the live one (a worker thread that outlives its test would
otherwise write the live file), and a per-test folder on top. A test that patches these itself
still works: its patch simply overrides these."""

import pytest

import cloud_quota
import main  # imported here so its import-time paths exist before any fixture runs


def _redirect(mp, d):
    mp.setattr(cloud_quota, "SECRETS_DIR", d)
    mp.setattr(cloud_quota, "CREDENTIALS_FILE", d / "app_credentials.json")
    mp.setattr(cloud_quota, "TOKENS_FILE", d / "tokens.json")
    mp.setattr(cloud_quota, "MANUAL_ACCOUNTS_FILE", d / "manual_accounts.json")
    mp.setattr(main, "_STATE_FILE", d / "state.json")
    mp.setattr(main, "_QUOTA_HISTORY_FILE", d / "quota_history.json")
    mp.setattr(main, "_INSTANCE_LOCK_FILE", d / "gui.lock")
    mp.setattr(main, "WORKSPACE_REPORT", d / "workspace_report.json")
    mp.setattr(main, "_SHOW_REQUEST_FILE", d / "show_request")


@pytest.fixture(autouse=True, scope="session")
def _session_secrets_baseline(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    _redirect(mp, tmp_path_factory.mktemp("secrets_baseline"))
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def _isolate_secrets_files(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path / "_secrets")
