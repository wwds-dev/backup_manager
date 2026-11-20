"""Shared fixtures. No test may touch the live ~/Library/Application Support/Backup Control Center
secrets files: every test gets the four secrets paths pointed at its own tmp_path. Tests that
patch these again themselves keep working (a later monkeypatch simply overrides this one)."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_secrets_files(monkeypatch, tmp_path):
    import cloud_quota
    d = tmp_path / "_secrets"
    monkeypatch.setattr(cloud_quota, "SECRETS_DIR", d)
    monkeypatch.setattr(cloud_quota, "CREDENTIALS_FILE", d / "app_credentials.json")
    monkeypatch.setattr(cloud_quota, "TOKENS_FILE", d / "tokens.json")
    monkeypatch.setattr(cloud_quota, "MANUAL_ACCOUNTS_FILE", d / "manual_accounts.json")
