"""A guard against an AppKit assertion that kills Qt apps on macOS 27.

Opening the menu bar icon's menu aborted Backup Control Center (crash reports
Backup Control Center-2026-10-07-151831.ips and -154310.ips): Qt's cocoa plugin
observes `NSMenuDidBeginTrackingNotification` and reads `clickCount` off the
current event, and on macOS 27 `-[NSEvent clickCount]` raises for an event that
is not a mouse event. The exception is thrown inside a CoreFoundation
notification callout, so nothing in Python can catch it.

The guard swaps in a `clickCount` that answers 0 for event types without a
click count and calls the original for the mouse events that have one.
`main()` installs it before `QApplication` exists.

This file is a deliberate copy of `lab_hub/ui/appkit_guard.py` (the original).
**The code below the docstring must stay byte-identical to it**, and
`tests/test_appkit_guard.py` fails when the two drift. Delete every copy
together when Qt ships a fixed cocoa plugin.
"""

from __future__ import annotations

import ctypes
import ctypes.util

# The event types that carry a click count. Everything else — key, system,
# application-defined, gesture, tablet — is what AppKit raises on.
MOUSE_EVENT_TYPES = frozenset(
    {
        1,  # LeftMouseDown          6  # LeftMouseDragged
        2,  # LeftMouseUp            7  # RightMouseDragged
        3,  # RightMouseDown        25  # OtherMouseDown
        4,  # RightMouseUp          26  # OtherMouseUp
        5,  # MouseMoved            27  # OtherMouseDragged
        6,
        7,
        25,
        26,
        27,
    }
)

# The replacement implementation must outlive the process: AppKit holds a raw
# function pointer to it, and a garbage-collected trampoline is a crash with a
# far worse stack than the one this fixes.
_KEEP: list = []

_CLICK_COUNT = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)


def _runtime():
    objc = ctypes.cdll.LoadLibrary(
        ctypes.util.find_library("objc") or "/usr/lib/libobjc.A.dylib"
    )
    ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AppKit.framework/AppKit")
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    objc.class_getInstanceMethod.restype = ctypes.c_void_p
    objc.class_getInstanceMethod.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    objc.method_getImplementation.restype = ctypes.c_void_p
    objc.method_getImplementation.argtypes = [ctypes.c_void_p]
    objc.method_setImplementation.restype = ctypes.c_void_p
    objc.method_setImplementation.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    return objc


def installed() -> bool:
    return bool(_KEEP)


def install() -> bool:
    """Make `clickCount` safe. Returns whether it is now guarded."""
    if installed():
        return True
    try:
        objc = _runtime()
        event_class = objc.objc_getClass(b"NSEvent")
        click_sel = objc.sel_registerName(b"clickCount")
        type_sel = objc.sel_registerName(b"type")
        method = objc.class_getInstanceMethod(event_class, click_sel)
        if not event_class or not method:
            return False

        original = _CLICK_COUNT(objc.method_getImplementation(method))

        event_type = objc.objc_msgSend
        event_type.restype = ctypes.c_ulong
        event_type.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        @_CLICK_COUNT
        def guarded(event, cmd):  # noqa: ANN001 - an ObjC IMP
            try:
                if event_type(event, type_sel) in MOUSE_EVENT_TYPES:
                    return original(event, cmd)
            except Exception:  # noqa: BLE001 - an IMP must never raise
                return 0
            return 0

        _KEEP.append(guarded)
        objc.method_setImplementation(method, ctypes.cast(guarded, ctypes.c_void_p))
        return True
    except (OSError, AttributeError, TypeError, ValueError):
        _KEEP.clear()
        return False
