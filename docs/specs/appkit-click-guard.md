# AppKit clickCount guard (macOS 27 menu bar abort)

**Problem.** Opening the menu bar icon's menu aborted Backup Control Center at
random (crash reports `Backup Control Center-2026-10-07-151831.ips` and
`-154310.ips`): `-[NSEvent clickCount]` raises inside `NSMenuDidBeginTracking`
when Qt's cocoa plugin reads it off a non-mouse event.

**User.** The owner, who keeps the app in the menu bar.

**Success measure.** Clicking the menu bar icon opens the menu without aborting,
on hardware, in the installed build; a subprocess test shows a non-mouse event's
`clickCount` answering 0 with the guard and aborting without it.

**Non-goals.** Anything else about the tray menu. No UI change.

**Architecture.** The lab's established fix, ported unchanged:
`appkit_guard.py` is a code-identical copy of `lab_hub/ui/appkit_guard.py`
(seventh copy), installed in `main()` before `QApplication`. A drift test pins it
to the original. The app has no `--selftest`, so the startup check is a stderr
warning if the install fails.

**Phases skipped.** Design (no UI), ADR (the decision was taken lab-wide on
2026-09-22 and is documented in `lab_hub/ui/appkit_guard.py`), Secure (no
network, secrets or untrusted input; one in-process method swap). Define and
Release gates: the owner requested the port, the rebuild and the commit directly.
