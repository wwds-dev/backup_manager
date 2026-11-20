"""The autouse fixture in conftest.py keeps every test off the live app-support folder
(Verify third pass, R2). These call the real writers with no per-test patching."""

import cloud_quota
import main


def test_real_writers_land_in_the_test_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "run_cmd", lambda *a, **k: (0, "12\t/x", ""))
    main._save_state({"k": 1})
    main._append_quota_sample("acct", 1, 2)
    main.icloud_local_bytes()
    for p in (main._STATE_FILE, main._QUOTA_HISTORY_FILE, main._INSTANCE_LOCK_FILE,
              cloud_quota.SECRETS_DIR / "icloud_du.log"):
        assert tmp_path in p.resolve().parents, f"{p} is outside the test folder"
    assert main._STATE_FILE.exists() and main._QUOTA_HISTORY_FILE.exists()
    assert (cloud_quota.SECRETS_DIR / "icloud_du.log").exists()


def test_every_secrets_and_state_writer_lands_in_the_test_folder(tmp_path):
    """One real-writer call per redirected path, so removing any single redirect in conftest fails."""
    import workspace_extra
    cloud_quota.save_app_credentials({"google": {"client_id": "a", "client_secret": "b"}})
    cloud_quota.save_tokens({"acct": {"provider": "google", "refresh_token": "t"}})
    cloud_quota.save_manual_accounts([{"key": "m", "name": "m"}])
    workspace_extra.write_report({"ok": True}, main.WORKSPACE_REPORT)
    main._SHOW_REQUEST_FILE.write_text("now")
    written = [cloud_quota.CREDENTIALS_FILE, cloud_quota.TOKENS_FILE,
               cloud_quota.MANUAL_ACCOUNTS_FILE, main.WORKSPACE_REPORT, main._SHOW_REQUEST_FILE]
    for p in written:
        assert p.exists(), f"{p} was not written"
        assert tmp_path in p.resolve().parents, f"{p} is outside the test folder"
