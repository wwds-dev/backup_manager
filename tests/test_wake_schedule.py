"""Reading the Wake Mac schedule back out of `pmset -g sched`.

The toggle used to look for "03:25" in the output, but pmset prints 12-hour
times without a leading zero (`3:25AM`), so after the password prompt succeeded
the toggle still read "disabled" — and clicking again just set it again.
"""

from __future__ import annotations

import main

# Captured from `pmset -g sched` on macOS 27 after enabling Wake Mac.
SCHED_ENABLED = """\
Repeating power events:
  wakepoweron at 3:25AM every day
Scheduled power events:
 [0]  wake at 10/06/2026 00:56:08 by 'com.apple.alarm.user-invisible-com.apple.osanalytics.hardhighengagementtimer'
 [1]  wake at 10/06/2026 02:36:35 by 'com.apple.alarm.user-invisible-com.apple.calaccessd.travelEngine.periodicRefreshTimer'
"""

SCHED_ONE_OFF_ONLY = """\
Scheduled power events:
 [0]  wake at 10/06/2026 03:25:00 by 'com.apple.alarm.user-invisible-something'
"""


def test_the_real_pmset_output_is_read_as_enabled():
    """The regression: `3:25AM` is the 03:25 wake the app set."""
    assert main.parse_repeating_wake(SCHED_ENABLED) == (3, 25)


def test_afternoon_times_are_converted_to_24_hour():
    assert main.parse_repeating_wake("Repeating power events:\n  wakepoweron at 2:05PM every day\n") == (14, 5)


def test_noon_and_midnight():
    assert main.parse_repeating_wake("Repeating power events:\n  wake at 12:00PM every day\n") == (12, 0)
    assert main.parse_repeating_wake("Repeating power events:\n  wake at 12:10AM every day\n") == (0, 10)


def test_one_off_system_wakes_do_not_count():
    """macOS schedules its own wakes; only the repeating event is ours."""
    assert main.parse_repeating_wake(SCHED_ONE_OFF_ONLY) is None


def test_nothing_scheduled():
    assert main.parse_repeating_wake("") is None


def test_wake_is_five_minutes_before_the_backup():
    assert main.wake_time_for_backup(3, 30) == (3, 25)


def test_wake_crosses_the_hour_and_midnight():
    assert main.wake_time_for_backup(4, 2) == (3, 57)
    assert main.wake_time_for_backup(0, 0) == (23, 55)
