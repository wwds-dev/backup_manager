"""The guard around AppKit's `clickCount` assertion, and its copy's drift.

macOS 27 made `-[NSEvent clickCount]` raise for events that have no click
count, and Qt's cocoa plugin asks for it whenever a menu begins tracking — so
opening the menu bar icon's menu aborted Backup Control Center
(Backup Control Center-2026-10-07-151831.ips, -154310.ips). These run against the real Objective-C
runtime; a mock of AppKit would be a mock of the thing being tested.

The crash case runs in a subprocess: unguarded, it terminates the interpreter,
which would take the whole test session with it rather than fail one test.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="AppKit only")

REPO = Path(__file__).resolve().parents[1]
ORIGINAL = REPO.parent / "lab_hub" / "ui" / "appkit_guard.py"

_PROBE = textwrap.dedent('''
    import ctypes, ctypes.util, sys
    sys.path.insert(0, {repo!r})
    import appkit_guard

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AppKit.framework/AppKit")
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    sel = lambda n: objc.sel_registerName(n.encode())

    if {install}:
        assert appkit_guard.install()

    other = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_ulong, CGPoint, ctypes.c_ulong, ctypes.c_double, ctypes.c_long,
        ctypes.c_void_p, ctypes.c_short, ctypes.c_long, ctypes.c_long)(
        ("objc_msgSend", objc))
    mouse = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_ulong, CGPoint, ctypes.c_ulong, ctypes.c_double, ctypes.c_long,
        ctypes.c_void_p, ctypes.c_long, ctypes.c_long, ctypes.c_float)(
        ("objc_msgSend", objc))
    count = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)(
        ("objc_msgSend", objc))
    NSEvent = objc.objc_getClass(b"NSEvent")

    double = mouse(NSEvent, sel("mouseEventWithType:location:modifierFlags:"
        "timestamp:windowNumber:context:eventNumber:clickCount:pressure:"),
        1, CGPoint(0, 0), 0, 0.0, 0, None, 0, 2, 1.0)
    print("mouse", count(double, sel("clickCount")), flush=True)

    app_defined = other(NSEvent, sel("otherEventWithType:location:modifierFlags:"
        "timestamp:windowNumber:context:subtype:data1:data2:"),
        15, CGPoint(0, 0), 0, 0.0, 0, None, 0, 0, 0)
    print("other", count(app_defined, sel("clickCount")), flush=True)
''')


def _probe(install: bool):
    return subprocess.run(
        [sys.executable, "-c", _PROBE.format(repo=str(REPO), install=install)],
        capture_output=True, text=True, timeout=60)


def test_unguarded_a_non_mouse_click_count_is_the_crash():
    """The control: proves the probe reaches the trap, so the guarded run
    below passing means something."""
    r = _probe(install=False)
    assert "mouse 2" in r.stdout
    assert "other" not in r.stdout and r.returncode != 0


def test_guarded_a_non_mouse_event_answers_zero_and_a_click_keeps_its_count():
    r = _probe(install=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split("\n")[:2] == ["mouse 2", "other 0"]


def test_installing_twice_is_harmless():
    """A second swizzle would call the first as its 'original' and recurse."""
    import appkit_guard

    assert appkit_guard.install()
    before = len(appkit_guard._KEEP)
    assert appkit_guard.install()
    assert len(appkit_guard._KEEP) == before


def test_main_installs_the_guard_before_the_application_exists():
    """Without it, opening the menu bar menu can abort the app."""
    src = (REPO / "main.py").read_text()
    body = src[src.index("def main():"):]
    assert "appkit_guard.install()" in body
    assert body.index("appkit_guard.install()") < body.index("QuitInterceptApp(sys.argv)")


def _code(path: Path) -> str:
    text = path.read_text()
    return text[text.index('"""', 3) + 3:]


@pytest.mark.skipif(not ORIGINAL.exists(), reason="lab_hub checkout not beside this repo")
def test_the_copy_matches_lab_hubs_original():
    assert _code(REPO / "appkit_guard.py") == _code(ORIGINAL), (
        "appkit_guard.py drifted from lab_hub/ui/appkit_guard.py — "
        "port the change to every copy")
