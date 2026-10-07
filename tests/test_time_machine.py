"""Reading `tmutil` output for the Time Machine card.

The card used to look for the word "Running" in `tmutil status`, which the idle
output contains (`Running = 0;`), so it said "backing up now…" and disabled its
button forever. These tests pin the parsing to the plist (`-X`) form instead.
"""

from __future__ import annotations

import plistlib

import main

# Captured from `tmutil status -X` on macOS 27 with Time Machine idle.
IDLE_STATUS = plistlib.dumps({"ClientID": "com.apple.backupd", "Percent": -1.0, "Running": False}).decode()

# Captured from `tmutil destinationinfo -X` with no backup disk chosen.
NO_DESTINATIONS = plistlib.dumps({}).decode()


def running_status(**extra):
    return plistlib.dumps({"ClientID": "com.apple.backupd", "Running": True, **extra}).decode()


# ----------------------------------------------------------------------
# Status
# ----------------------------------------------------------------------
def test_idle_is_not_reported_as_running():
    """The regression: `Running = 0` is not a backup in progress."""
    assert main.parse_tm_status(IDLE_STATUS) == (False, None, None)


def test_a_running_backup_reports_its_phase_and_progress():
    xml = running_status(BackupPhase="Copying", Progress={"Percent": 0.42})
    assert main.parse_tm_status(xml) == (True, "Copying", 42)


def test_a_running_backup_without_progress_still_counts():
    assert main.parse_tm_status(running_status(Percent=-1.0)) == (True, None, None)


def test_unreadable_status_is_idle():
    assert main.parse_tm_status("") == (False, None, None)


# ----------------------------------------------------------------------
# Destinations
# ----------------------------------------------------------------------
def test_no_destination_means_not_set_up():
    assert main.tm_has_destination(NO_DESTINATIONS) is False


def test_a_configured_disk_is_a_destination():
    xml = plistlib.dumps({"Destinations": [{"Name": "TM Disk", "Kind": "Local"}]}).decode()
    assert main.tm_has_destination(xml) is True


def test_unparseable_destination_info_does_not_claim_tm_is_off():
    assert main.tm_has_destination("tmutil: something unexpected") is True


# ----------------------------------------------------------------------
# Latest backup
# ----------------------------------------------------------------------
def test_latest_backup_is_shown_as_a_date():
    out = "/Volumes/.timemachine/ABC/2026-10-06-213015.backup/2026-10-06-213015.backup\n"
    assert main.describe_tm_latest(out, "") == "2026-10-06 21:30"


def test_an_unplugged_disk_is_not_reported_as_no_backups():
    """tmutil exits 0 with the reason on stderr; that is not "none found"."""
    err = 'Failed to mount backup destination, error: ... "Failed to mount destination."'
    assert main.describe_tm_latest("", err) == "unknown — backup disk not connected"


def test_no_output_at_all_is_none_found():
    assert main.describe_tm_latest("", "") == "none found"


def test_an_unrecognised_name_is_shown_as_is():
    assert main.describe_tm_latest("/Volumes/x/Latest\n", "") == "Latest"
