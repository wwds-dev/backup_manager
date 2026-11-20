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
