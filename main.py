#!/usr/bin/env python3
"""
Backup Control Center
=====================
One place to monitor your cloud services and manage the custom Google Drive backup
(the rsync job + launchd schedule we built). It does NOT try to reconfigure the
proprietary sync engines of iCloud / Google Drive / Dropbox / Proton Drive — those
stay in their own apps. Instead it gives a unified dashboard plus full control of the
backup layer we own, and quick launchers into each service.

Run:  python main.py   (needs PySide6 — see requirements.txt)
"""

import sys
import ctypes
import ctypes.util
import fcntl
import glob
import json
import os
import plistlib
import re
import shutil
import subprocess
import urllib.request

import version
from datetime import datetime
from pathlib import Path

# Headless mode: launchd calls the .app with --run-backup instead of /bin/bash directly.
# This lets the app's FDA grant cover the subprocess, bypassing the /bin/bash TCC block.
if "--run-backup" in sys.argv:
    _script = Path.home() / "Documents" / "lab" / "_Admin" / "backup" / "backup_to_gdrive.sh"
    sys.exit(subprocess.run(["/bin/bash", str(_script)]).returncode)

import signal as _signal
from PySide6.QtCore import (
    Qt, QThread, Signal, QProcess, QTimer, QProcessEnvironment, QEvent,
    QFileSystemWatcher, QPointF, QRect, QSize, QPoint, QObject,
)
from PySide6.QtGui import QTextCursor, QColor, QIcon, QPixmap, QPainter, QPen, QPolygonF
from PySide6.QtNetwork import QNetworkInformation
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QListWidget, QTextEdit, QTextBrowser, QFileDialog, QMessageBox, QDialog,
    QPlainTextEdit, QFrame, QScrollArea, QProgressBar,
    QGraphicsDropShadowEffect, QSizePolicy, QLineEdit, QFormLayout, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSystemTrayIcon, QMenu, QCheckBox, QSpinBox,
    QLayout, QAbstractScrollArea,
)

import cloud_quota

# Set only by the tray's Quit action. Every other quit path — Cmd+Q, the dock's
# Quit item, closing the window — is turned into "hide to the menu bar" so the
# nightly schedule, network trigger and USB trigger keep running.
_REALLY_QUITTING: bool = False

# Set by main() before creating QApplication; used by widgets that need to
# apply different inline styles for dark/light mode.
_DARK: bool = False


# ----------------------------------------------------------------------------
# Dock icon visibility
#
# Hiding the window is not enough to make a refused Quit feel like a quit — the
# dock icon stays behind. macOS controls that with the app's activation policy,
# which Qt does not expose, so call -[NSApplication setActivationPolicy:]
# through the Objective-C runtime. Accessory keeps the menu bar icon (an
# NSStatusItem) while dropping the dock tile and the app menu.
# ----------------------------------------------------------------------------
_NS_ACTIVATION_POLICY_REGULAR = 0
_NS_ACTIVATION_POLICY_ACCESSORY = 1

try:
    _objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    _objc.objc_getClass.restype = ctypes.c_void_p
    _objc.objc_getClass.argtypes = [ctypes.c_char_p]
    _objc.sel_registerName.restype = ctypes.c_void_p
    _objc.sel_registerName.argtypes = [ctypes.c_char_p]
except Exception:
    _objc = None


def _set_dock_icon_visible(visible: bool) -> bool:
    """Show or hide the dock tile. Returns True if the policy was applied."""
    if _objc is None:
        return False
    try:
        # objc_msgSend needs a distinct prototype per signature, so cast twice.
        send_id = ctypes.cast(
            _objc.objc_msgSend,
            ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p))
        send_policy = ctypes.cast(
            _objc.objc_msgSend,
            ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
                             ctypes.c_long))
        ns_app = send_id(_objc.objc_getClass(b"NSApplication"),
                         _objc.sel_registerName(b"sharedApplication"))
        if not ns_app:
            return False
        policy = (_NS_ACTIVATION_POLICY_REGULAR if visible
                  else _NS_ACTIVATION_POLICY_ACCESSORY)
        return bool(send_policy(
            ns_app, _objc.sel_registerName(b"setActivationPolicy:"), policy))
    except Exception:
        return False

# ----------------------------------------------------------------------------
# Paths / config
# ----------------------------------------------------------------------------
HOME = Path.home()
DOCS = HOME / "Documents"
BACKUP_DIR = DOCS / "lab" / "_Admin" / "backup"
SCRIPT = BACKUP_DIR / "backup_to_gdrive.sh"
FOLDERS_FILE = BACKUP_DIR / "backup_folders.txt"
EXCLUDES_FILE = BACKUP_DIR / "gdrive_backup_excludes.txt"
LOG_DIR = BACKUP_DIR / "logs"
PLIST_SRC = BACKUP_DIR / "com.andreas.gdrive-backup.plist"
PLIST_DST = HOME / "Library" / "LaunchAgents" / "com.andreas.gdrive-backup.plist"
LAUNCHD_LABEL = "com.andreas.gdrive-backup"
CLOUD_DIR = HOME / "Library" / "CloudStorage"
ICLOUD_DIR = HOME / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
# The mount itself. Pre-flight checks test THIS, not DEST_ROOT: the destination
# is created by the backup script's mkdir -p, so a missing one is normal on a
# first run or after the Drive copy is cleared out. Testing DEST_ROOT reported
# "Google Drive not mounted" for a perfectly healthy mount and blocked the very
# run that would have recreated the folder.
DRIVE_ROOT = CLOUD_DIR / "GoogleDrive-andreas.seel86@gmail.com" / "My Drive"
DEST_ROOT = DRIVE_ROOT / "Backups" / "MacBook" / "Documents"
LAB_ACTIVE = DOCS / "lab" / "active"
# Same disposable-junk names as gdrive_backup_excludes.txt — if it's not worth
# backing up, it's not worth keeping locally once the project is idle either.
DISPOSABLE_DIR_NAMES = {
    ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "node_modules", ".cache", "dist", "build",
}


# ----------------------------------------------------------------------------
# Style (dynamic — built once at startup based on system dark/light mode)
# ----------------------------------------------------------------------------
def build_app_style(dark: bool) -> str:
    # iOS / macOS Human Interface Guideline palette
    if dark:
        page     = "#1C1C1E"   # systemBackground (dark)
        card     = "#2C2C2E"   # secondarySystemBackground (dark)
        card_bdr = "#38383A"   # separator (dark)
        text     = "#FFFFFF"   # label (dark)
        sec      = "#98989D"   # secondaryLabel (dark)
        tile_bg  = "#3A3A3C"   # tertiarySystemFill (dark)
        tile_bdr = "#48484A"
        acc      = "#0A84FF"   # systemBlue (dark)
        acc_hov  = "#0070E0"
        acc_prs  = "#005EC7"
        sec_bg   = "#3A3A3C"   # systemFill (dark)
        sec_hov  = "#48484A"
        inp_bg   = "#2C2C2E"
        inp_bdr  = "#48484A"
        inp_foc  = "#0A84FF"
        dis_bg   = "#2C2C2E"
        dis_fg   = "#48484A"
        link_clr = "#0A84FF"
        link_hov = "#0A2A4A"
        danger   = "#FF453A"   # systemRed (dark)
        danger_h = "#D93830"
        list_bg  = "#2C2C2E"
        list_bdr = "#38383A"
        sel_bg   = "#0A84FF33"
        hdr_bg   = "#3A3A3C"
        menu_bg  = "#2C2C2E"
        menu_bdr = "#38383A"
    else:
        page     = "#F2F2F7"   # systemBackground (light)
        card     = "#FFFFFF"   # secondarySystemBackground (light)
        card_bdr = "#C6C6C8"   # separator (light)
        text     = "#1C1C1E"   # label (light)
        sec      = "#636366"   # secondaryLabel (light)
        tile_bg  = "#F9F9FB"   # tertiarySystemFill (light)
        tile_bdr = "#E5E5EA"
        acc      = "#007AFF"   # systemBlue (light)
        acc_hov  = "#006BE0"
        acc_prs  = "#005BC7"
        sec_bg   = "#E5E5EA"   # systemFill (light)
        sec_hov  = "#D1D1D6"
        inp_bg   = "#FFFFFF"
        inp_bdr  = "#C6C6C8"
        inp_foc  = "#007AFF"
        dis_bg   = "#E5E5EA"
        dis_fg   = "#AEAEB2"
        link_clr = "#007AFF"
        link_hov = "#EFF6FF"
        danger   = "#FF3B30"   # systemRed (light)
        danger_h = "#E0342A"
        list_bg  = "#FFFFFF"
        list_bdr = "#E5E5EA"
        sel_bg   = "#007AFF22"
        hdr_bg   = "#F2F2F7"
        menu_bg  = "#FFFFFF"
        menu_bdr = "#C6C6C8"

    return f"""
/* ── Base: colour + font only — NO background.
   Setting background here would paint every child widget with the page
   colour, creating visible dark boxes inside lighter cards. Instead each
   container sets its own background explicitly. ── */
QWidget {{
    color: {text};
    font-size: 13px;
}}

/* ── Page background — only on outer containers ── */
QMainWindow, QScrollArea, QAbstractScrollArea,
#ScrollArea, #ScrollContent, QDialog {{
    background: {page};
    border: none;
}}

/* ── Labels and other passive widgets: transparent
   so the parent container's background shows through ── */
QLabel {{
    background: transparent;
    color: {text};
}}

/* ── App header ─────────────────────────────────── */
#AppTitle {{
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -0.3px;
}}
#AppSubtitle {{
    color: {sec};
    font-size: 12px;
}}

/* ── Cards ──────────────────────────────────────── */
#Card {{
    background: {card};
    border-radius: 12px;
    border: 1px solid {card_bdr};
}}
#CardTitle {{
    font-size: 13px;
    font-weight: 600;
    letter-spacing: -0.1px;
}}
#CardSubtitle {{
    color: {sec};
    font-size: 11px;
}}

/* ── Storage tiles ──────────────────────────────── */
#StorageTile {{
    background: {tile_bg};
    border-radius: 10px;
    border: 1px solid {tile_bdr};
}}
#TileName {{
    font-weight: 600;
    font-size: 12px;
}}
#TileAccount {{
    font-size: 10px;
    color: {sec};
}}
#TileStatus {{
    font-size: 11px;
    color: {sec};
}}
#TileFree {{
    font-size: 11px;
    color: {sec};
}}

/* ── Buttons — primary ──────────────────────────── */
QPushButton {{
    background: {acc};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 7px 16px;
    font-weight: 600;
    font-size: 13px;
}}
QPushButton:hover {{
    background: {acc_hov};
}}
QPushButton:pressed {{
    background: {acc_prs};
}}
QPushButton:disabled {{
    background: {dis_bg};
    color: {dis_fg};
}}

/* ── Buttons — secondary ────────────────────────── */
QPushButton[secondary="true"] {{
    background: {sec_bg};
    color: {text};
    border: none;
}}
QPushButton[secondary="true"]:hover {{
    background: {sec_hov};
}}
QPushButton[secondary="true"]:disabled {{
    background: {dis_bg};
    color: {dis_fg};
}}

/* ── Buttons — danger ───────────────────────────── */
QPushButton[danger="true"] {{
    background: {danger};
    color: white;
}}
QPushButton[danger="true"]:hover {{
    background: {danger_h};
}}

/* ── Buttons — link / inline ────────────────────── */
QPushButton[link="true"] {{
    background: transparent;
    color: {link_clr};
    text-align: left;
    padding: 4px 2px;
    font-weight: 500;
    border: none;
}}
QPushButton[link="true"]:hover {{
    color: {acc_hov};
    background: {link_hov};
    border-radius: 4px;
}}

/* ── Lists & tables ─────────────────────────────── */
QListWidget {{
    background: {list_bg};
    border: 1px solid {list_bdr};
    border-radius: 8px;
    padding: 4px;
    outline: 0;
}}
QListWidget::item {{
    border-radius: 5px;
    padding: 3px 6px;
}}
QListWidget::item:selected {{
    background: {sel_bg};
    color: {text};
}}
QTableWidget {{
    background: {list_bg};
    border: 1px solid {list_bdr};
    border-radius: 8px;
    gridline-color: {list_bdr};
    outline: 0;
}}
QTableWidget::item {{
    padding: 0 10px;  /* the header sections' inset, so text lines up under its heading */
}}
QTableWidget::item:selected {{
    background: {sel_bg};
    color: {text};
}}
QHeaderView::section {{
    background: {hdr_bg};
    color: {sec};
    border: none;
    border-bottom: 1px solid {list_bdr};
    padding: 5px 10px;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
}}

/* ── Inputs ─────────────────────────────────────── */
QLineEdit {{
    background: {inp_bg};
    color: {text};
    border: 1px solid {inp_bdr};
    border-radius: 8px;
    padding: 6px 10px;
}}
QLineEdit:focus {{
    border: 1.5px solid {inp_foc};
}}

/* ── Dialogs ────────────────────────────────────── */
QDialog {{
    background: {page};
}}

/* ── Log / code output (always dark terminal) ───── */
QTextEdit, QPlainTextEdit {{
    background: #0D1117;
    color: #C9D1D9;
    border: 1px solid {"#30363D" if dark else "#D0D7DE"};
    border-radius: 8px;
    font-family: Menlo, "SF Mono", Consolas, monospace;
    font-size: 11px;
    padding: 4px;
}}

/* ── Progress bars ──────────────────────────────── */
QProgressBar {{
    border: none;
    border-radius: 4px;
    background: {tile_bdr};
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    border-radius: 4px;
    background: {acc};
}}

/* ── Menus ──────────────────────────────────────── */
QMenu {{
    background: {menu_bg};
    color: {text};
    border: 1px solid {menu_bdr};
    border-radius: 8px;
    padding: 4px 0;
}}
QMenu::item {{
    padding: 6px 20px;
    border-radius: 0px;
}}
QMenu::item:selected {{
    background: {acc};
    color: white;
}}
QMenu::separator {{
    height: 1px;
    background: {menu_bdr};
    margin: 3px 8px;
}}

/* ── Scroll bars (subtle) ───────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {"#48484A" if dark else "#C6C6C8"};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {"#48484A" if dark else "#C6C6C8"};
    border-radius: 3px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
"""


def shadow():
    eff = QGraphicsDropShadowEffect()
    eff.setBlurRadius(12)
    eff.setOffset(0, 2)
    eff.setColor(QColor(0, 0, 0, 18))
    return eff


class Card(QFrame):
    def __init__(self, title=None, subtitle=None):
        super().__init__()
        self.setObjectName("Card")
        self.setGraphicsEffect(shadow())
        self.vbox = QVBoxLayout(self)
        self.vbox.setContentsMargins(18, 16, 18, 18)
        self.vbox.setSpacing(10)
        if title:
            head = QVBoxLayout()
            head.setSpacing(2)
            t = QLabel(title)
            t.setObjectName("CardTitle")
            head.addWidget(t)
            if subtitle:
                s = QLabel(subtitle)
                s.setObjectName("CardSubtitle")
                head.addWidget(s)
            self.vbox.addLayout(head)

    def body(self, widget_or_layout):
        if isinstance(widget_or_layout, QWidget):
            self.vbox.addWidget(widget_or_layout)
        else:
            self.vbox.addLayout(widget_or_layout)


def secondary_button(text):
    b = QPushButton(text)
    b.setProperty("secondary", True)
    return b


def link_button(text):
    b = QPushButton(text)
    b.setProperty("link", True)
    return b


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def human_size(num_bytes):
    n = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def run_cmd(args, timeout=60):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return 1, "", str(e)


def read_folders():
    folders = []
    if FOLDERS_FILE.exists():
        for raw in FOLDERS_FILE.read_text().splitlines():
            line = raw.split("#", 1)[0].strip()
            if line:
                folders.append(line)
    return folders


def write_folders(folders):
    header = (
        "# Folders under ~/Documents to back up to Google Drive.\n"
        "# One folder (relative to ~/Documents) per line. '#' lines are ignored.\n"
        "# Edited by hand or by the Backup Control Center app.\n"
    )
    FOLDERS_FILE.write_text(header + "\n".join(folders) + "\n")


def launchd_loaded():
    rc, out, _ = run_cmd(["launchctl", "list"], timeout=15)
    return LAUNCHD_LABEL in out


WAKE_LEAD_MIN = 5


def wake_time_for_backup(hour, minute):
    """The wake time that precedes a backup at hour:minute by WAKE_LEAD_MIN."""
    total = (hour * 60 + minute - WAKE_LEAD_MIN) % (24 * 60)
    return divmod(total, 60)


def parse_repeating_wake(sched_out):
    """`pmset -g sched` -> (hour, minute) of the repeating wake, or None.

    pmset prints `wakepoweron at 3:25AM every day` — 12-hour, no leading zero —
    so searching for "03:25" never matched and the toggle read "disabled" forever.
    Only the "Repeating power events" block counts; the one-off events below it
    are macOS's own timers and come and go.
    """
    in_repeating = False
    for line in sched_out.splitlines():
        if line.strip().endswith(":") and not line.startswith(" "):
            in_repeating = line.startswith("Repeating power events")
            continue
        if not in_repeating:
            continue
        m = re.search(r"\bwake\w*\s+at\s+(\d{1,2}):(\d{2})\s*([AP]M)", line, re.I)
        if m:
            h, mins, ampm = int(m.group(1)), int(m.group(2)), m.group(3).upper()
            h = h % 12 + (12 if ampm == "PM" else 0)
            return h, mins
    return None


def current_wake_schedule():
    _, out, _ = run_cmd(["pmset", "-g", "sched"], timeout=10)
    return parse_repeating_wake(out)


def set_wake_schedule(enable, hour=3, minute=25):
    if enable:
        cmd = f"pmset repeat wakeorpoweron MTWRFSU {hour:02d}:{minute:02d}:00"
    else:
        cmd = "pmset repeat cancel"
    rc, _, err = run_cmd([
        "osascript", "-e",
        f'do shell script "{cmd}" with administrator privileges',
    ], timeout=60)
    return rc == 0, err


def cloud_services():
    rows = []
    if CLOUD_DIR.exists():
        for p in sorted(CLOUD_DIR.iterdir()):
            if p.name.startswith("."):
                continue
            rows.append((p.name, p, p.exists()))
    rows.append(("iCloud Drive", ICLOUD_DIR, ICLOUD_DIR.exists()))
    return rows


def icloud_local_bytes() -> int | None:
    """Bytes used by the local iCloud cache, or None if unavailable."""
    rc, out, _ = run_cmd(["du", "-sk", str(HOME / "Library" / "Mobile Documents")], timeout=30)
    if rc == 0 and out:
        try:
            return int(out.split("\t", 1)[0]) * 1024
        except ValueError:
            pass
    return None


def storage_targets():
    """(name, path, exists) for Local Disk plus mounts that can show real account
    quota (Google Drive, Dropbox). Proton Drive / iCloud Drive have no public quota
    API, so showing them here would just repeat the Local Disk number — they're
    left out rather than displayed as a misleading duplicate.
    Deduplicates by base account email — keeps the shortest (cleanest) folder name
    when Google Drive creates multiple mounts for the same account."""
    rows = [("Local Disk", HOME, True)]
    seen = {}  # base_email -> (name, path, exists)
    for name, path, exists in cloud_services():
        if not cloud_quota.provider_for_name(name):
            continue
        _, account = split_tile_name(name)
        base = re.sub(r'\s+\(\d{2}-\d{2}-\d{4}.*\)$', '', account).strip()
        key = (cloud_quota.provider_for_name(name), base)
        if key not in seen or len(name) < len(seen[key][0]):
            seen[key] = (name, path, exists)
    rows.extend(seen.values())
    return rows


def split_tile_name(name):
    """Split a CloudStorage folder name into (provider, account) for display."""
    if name.startswith("GoogleDrive-"):
        return "Google Drive", name[len("GoogleDrive-"):]
    if name.startswith("ProtonDrive-"):
        account = name[len("ProtonDrive-"):]
        account = re.sub(r"-folder\b", "", account)
        return "Proton Drive", account
    if name.startswith("Dropbox"):
        account = name[len("Dropbox"):].strip()
        return "Dropbox", account
    return name, ""


def disk_usage_for(path):
    """Free/total/used for the filesystem backing `path`, or None if unavailable."""
    try:
        if not Path(path).exists():
            return None
        return shutil.disk_usage(str(path))
    except OSError:
        return None


def iter_log_runs(text: str):
    """Yield (date, start_time, block) for each backup run in one daily log.

    A daily log accumulates: every run that day appends to the same file. So a
    plain search over the whole file always describes the day's FIRST run and
    never updates as later runs land. Split on the start markers instead and let
    callers pick the run they mean — almost always the last one.
    """
    starts = list(re.finditer(
        r"\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})\] ===== Backup run started", text))
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        yield m.group(1), m.group(2), text[m.start():end]


def run_status(block: str) -> str:
    """OK / ERRORS / — for a single run's block."""
    if "finished OK" in block:
        return "OK"
    if "WITH ERRORS" in block:
        return "ERRORS"
    return "—"


def run_finished_at(block: str) -> str | None:
    m = re.search(
        r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+===== Backup run finished", block)
    return m.group(1) if m else None


def _newest_log_runs():
    """Runs from the newest log that has any, newest run first."""
    for log_path in sorted(glob.glob(str(LOG_DIR / "backup_*.log")), reverse=True):
        text = Path(log_path).read_text(errors="replace")
        runs = list(iter_log_runs(text))
        if runs:
            return log_path, list(reversed(runs))
    return None, []


def last_backup_info():
    logs = sorted(glob.glob(str(LOG_DIR / "backup_*.log")))
    if not logs:
        return "No backups run yet.", ""
    log_path, runs = _newest_log_runs()
    if not runs:
        latest = logs[-1]
        stamp = Path(latest).stem.replace("backup_", "")
        return f"Last run: {stamp}  —  unknown", latest
    date, started, block = runs[0]
    # Status comes from this run's block only. Scanning the whole file meant one
    # early success hid every later failure that day.
    timestamp = run_finished_at(block) or f"{date} {started}"
    return f"Last run: {timestamp}  —  {run_status(block)}", log_path


def last_backup_age_hours() -> float | None:
    """Hours since the last successful backup finished, or None if no record."""
    for log_path in sorted(glob.glob(str(LOG_DIR / "backup_*.log")), reverse=True):
        text = Path(log_path).read_text(errors="replace")
        for _date, _started, block in reversed(list(iter_log_runs(text))):
            if "finished OK" not in block:
                continue
            stamp = run_finished_at(block)
            if not stamp:
                continue
            try:
                t = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            return (datetime.now() - t).total_seconds() / 3600
    return None


def last_sync_per_folder() -> dict:
    """Return {folder_name: 'YYYY-MM-DD HH:MM:SS'} from each folder's newest OK line."""
    result = {}
    logs = sorted(glob.glob(str(LOG_DIR / "backup_*.log")), reverse=True)
    for log_path in logs:
        text = Path(log_path).read_text(errors="replace")
        # Newest run first, so the first time a folder is seen is its latest sync.
        for _date, _started, block in reversed(list(iter_log_runs(text))):
            for m in re.finditer(
                    r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+OK: (.+)", block):
                result.setdefault(m.group(2).strip(), m.group(1))
        if len(result) >= 50:
            break
    return result


def _system_dark_mode() -> bool:
    rc, out, _ = run_cmd(["defaults", "read", "-g", "AppleInterfaceStyle"], timeout=5)
    return out.strip().lower() == "dark"


def _notify(title: str, message: str, subtitle: str = "") -> None:
    sub = f'subtitle "{subtitle}" ' if subtitle else ""
    subprocess.Popen(
        ["osascript", "-e",
         f'display notification "{message}" with title "{title}" {sub}'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


# Starting at login is a LaunchAgent rather than a System Events login item,
# because a login item cannot pass arguments and this app needs --background: a
# menu-bar resident should come up in the menu bar, not open a window and steal
# the dock and the foreground while you are still logging in. Same shape as Lab
# Hub's com.netrunner3000.labhub.login.
APP_BUNDLE = Path("/Applications/Backup Control Center.app")
LOGIN_AGENT_LABEL = "com.wwds-dev.backup-control-center.login"
LOGIN_AGENT_PLIST = HOME / "Library" / "LaunchAgents" / f"{LOGIN_AGENT_LABEL}.plist"

_LOGIN_AGENT_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>Label</key>
\t<string>{label}</string>
\t<key>ProgramArguments</key>
\t<array>
\t\t<string>/usr/bin/open</string>
\t\t<string>-a</string>
\t\t<string>{app}</string>
\t\t<string>--args</string>
\t\t<string>--background</string>
\t</array>
\t<key>RunAtLoad</key>
\t<true/>
</dict>
</plist>
"""


def _legacy_login_item() -> bool:
    """The old System Events login item, kept only so it can be cleaned up."""
    _, out, _ = run_cmd(
        ["osascript", "-e",
         'tell application "System Events" to return (name of login items) contains "Backup Control Center"'],
        timeout=10,
    )
    return out.strip().lower() == "true"


def _remove_legacy_login_item() -> None:
    if _legacy_login_item():
        run_cmd(["osascript", "-e",
                 'tell application "System Events" to delete login item "Backup Control Center"'],
                timeout=10)


def is_login_item() -> bool:
    return LOGIN_AGENT_PLIST.exists() or _legacy_login_item()


def set_login_item(enable: bool) -> tuple:
    if enable:
        if not APP_BUNDLE.exists():
            return False, (f"{APP_BUNDLE} is not installed.\n"
                           "Run build_app.sh first — a LaunchAgent opens the bundle, "
                           "not this checkout.")
        try:
            LOGIN_AGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
            LOGIN_AGENT_PLIST.write_text(
                _LOGIN_AGENT_TEMPLATE.format(label=LOGIN_AGENT_LABEL, app=APP_BUNDLE))
        except OSError as e:
            return False, str(e)
        run_cmd(["launchctl", "unload", str(LOGIN_AGENT_PLIST)], timeout=15)
        rc, _, err = run_cmd(["launchctl", "load", str(LOGIN_AGENT_PLIST)], timeout=15)
        # A login item and the agent would both fire; the agent is the one that
        # can ask for --background, so the login item goes.
        _remove_legacy_login_item()
        return rc == 0, err
    run_cmd(["launchctl", "unload", str(LOGIN_AGENT_PLIST)], timeout=15)
    try:
        LOGIN_AGENT_PLIST.unlink(missing_ok=True)
    except OSError as e:
        return False, str(e)
    _remove_legacy_login_item()
    return True, ""


def migrate_login_item() -> None:
    """Convert an existing login item to the background LaunchAgent, once.

    Without this, someone who enabled "Open at login" before would keep getting
    the window and the dock tile at every login until they toggled the setting
    off and on again.
    """
    if LOGIN_AGENT_PLIST.exists() or not _legacy_login_item():
        return
    set_login_item(True)


# ----------------------------------------------------------------------------
# App state persistence (notification cooldown, preferences)
# ----------------------------------------------------------------------------
_STATE_FILE = cloud_quota.SECRETS_DIR / "state.json"


def _load_state() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text())
        except (ValueError, OSError):
            return {}
    return {}


def _save_state(data: dict) -> None:
    cloud_quota.SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(data, indent=2))


# How long an overdue-backup notice stays quiet after being sent. Persisted to
# state.json rather than kept in memory: the app is a menu-bar resident that
# gets relaunched, and a cooldown that resets on restart is no cooldown at all —
# a login loop would notify every time.
OVERDUE_COOLDOWN_S = 3600
_OVERDUE_KEY = "last_overdue_notify"


def overdue_notice_due(last, now, cooldown: float = OVERDUE_COOLDOWN_S) -> bool:
    """Whether an overdue notice may be sent again yet."""
    if last is None:
        return True
    return (now - last).total_seconds() >= cooldown


def load_overdue_stamp():
    """When the last overdue notice went out, across restarts."""
    raw = _load_state().get(_OVERDUE_KEY)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def save_overdue_stamp(when) -> None:
    state = _load_state()
    state[_OVERDUE_KEY] = when.isoformat()
    _save_state(state)


_QUOTA_HISTORY_FILE = cloud_quota.SECRETS_DIR / "quota_history.json"
_QUOTA_HISTORY_MAX = 60  # samples per account key


def _load_quota_history() -> dict:
    if _QUOTA_HISTORY_FILE.exists():
        try:
            return json.loads(_QUOTA_HISTORY_FILE.read_text())
        except (ValueError, OSError):
            return {}
    return {}


def _append_quota_sample(account_key: str, used: int, total: int) -> None:
    history = _load_quota_history()
    samples = history.get(account_key, [])
    samples.append({"ts": datetime.now().isoformat(timespec="minutes"), "used": used, "total": total})
    samples = samples[-_QUOTA_HISTORY_MAX:]
    history[account_key] = samples
    try:
        cloud_quota.SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        _QUOTA_HISTORY_FILE.write_text(json.dumps(history))
    except OSError:
        pass


def _get_quota_history(account_key: str) -> list:
    return _load_quota_history().get(account_key, [])


# ----------------------------------------------------------------------------
# Background worker for folder sizes (keeps UI responsive)
# ----------------------------------------------------------------------------
_retired_workers = set()


def replace_worker(old, new):
    """Start `new`; keep a still-running `old` alive until it finishes.

    Dropping the last reference to a running QThread aborts the whole app
    ("QThread: Destroyed while thread is still running"), and assigning a new
    scan over one still in flight does exactly that — Refresh all, or adding
    a folder during a long size scan. The superseded scan is also cut off from
    its slot, so its stale result cannot land on top of the new one.
    """
    if old is not None and old.isRunning():
        try:
            old.done.disconnect()
        except (RuntimeError, TypeError):
            pass
        _retired_workers.add(old)
        old.finished.connect(lambda w=old: _retired_workers.discard(w))
    new.start()
    return new


class SizeWorker(QThread):
    done = Signal(dict, str)  # {folder: size}, total_str

    def __init__(self, folders):
        super().__init__()
        self.folders = folders

    def run(self):
        # One `du` per folder: these are the whole backup set, and walking
        # each twice (once for the row, once for the total) doubled the wait.
        sizes = {}
        total = 0
        for f in self.folders:
            p = DOCS / f
            sizes[f] = "—"
            rc, out, _ = run_cmd(["du", "-sk", str(p)], timeout=120) if p.exists() else (1, "", "")
            if rc == 0 and out:
                try:
                    n = int(out.split("\t", 1)[0]) * 1024
                except ValueError:
                    sizes[f] = "?"
                    continue
                sizes[f] = human_size(n)
                total += n
        self.done.emit(sizes, human_size(total))


class LabHealthWorker(QThread):
    """Scans lab/active/<project> for disk hogs, git hygiene, and missing manifests."""
    done = Signal(list)  # list of row dicts

    def run(self):
        rows = []
        if LAB_ACTIVE.exists():
            for proj in sorted(LAB_ACTIVE.iterdir()):
                if proj.is_dir() and not proj.name.startswith("."):
                    rows.append(self._scan_project(proj))
        self.done.emit(rows)

    @classmethod
    def _scan_project(cls, proj):
        total_kb = cls._size_kb(proj)
        reclaim_items = [(p, cls._size_kb(p)) for p in cls._find_disposable(proj)]
        reclaim_kb = sum(kb for _, kb in reclaim_items)

        has_git = (proj / ".git").is_dir()
        uncommitted, last_commit = 0, "—"
        if has_git:
            _, out, _ = run_cmd(["git", "-C", str(proj), "status", "--porcelain"], timeout=20)
            uncommitted = len([l for l in out.splitlines() if l.strip()])
            _, out2, _ = run_cmd(
                ["git", "-C", str(proj), "log", "-1", "--format=%ad", "--date=short"], timeout=20)
            last_commit = out2.strip() or "—"

        has_manifest = (proj / "requirements.txt").exists() or (proj / "pyproject.toml").exists()

        env_flag = ""
        if (proj / ".env").exists():
            if has_git:
                rc, _, _ = run_cmd(["git", "-C", str(proj), "check-ignore", "-q", ".env"], timeout=10)
                env_flag = "" if rc == 0 else "⚠️ .env not git-ignored"
            else:
                env_flag = ".env present (no git repo to check)"

        return {
            "name": proj.name,
            "total_kb": total_kb,
            "reclaim_kb": reclaim_kb,
            "reclaim_items": reclaim_items,
            "has_git": has_git,
            "uncommitted": uncommitted,
            "last_commit": last_commit,
            "has_manifest": has_manifest,
            "env_flag": env_flag,
        }

    @staticmethod
    def _size_kb(path):
        rc, out, _ = run_cmd(["du", "-sk", str(path)], timeout=120)
        if rc == 0 and out:
            try:
                return int(out.split("\t", 1)[0])
            except ValueError:
                pass
        return 0

    @staticmethod
    def _find_disposable(proj):
        """Top-most matching dirs only (-prune) so nested __pycache__ inside a
        .venv isn't counted twice, and every match is independently rm-able."""
        names = sorted(DISPOSABLE_DIR_NAMES)
        name_expr = []
        for i, n in enumerate(names):
            if i:
                name_expr.append("-o")
            name_expr += ["-name", n]
        args = ["find", str(proj), "-mindepth", "1", "-type", "d",
                "(", *name_expr, ")", "-prune", "-print"]
        rc, out, _ = run_cmd(args, timeout=60)
        if rc != 0:
            return []
        return [Path(p) for p in out.splitlines() if p.strip()]


# ----------------------------------------------------------------------------
# Storage overview card (free space per mount)
# ----------------------------------------------------------------------------
TILE_WIDTH = 230


class SparklineWidget(QWidget):
    """Mini line chart showing % quota used over the last N samples."""

    def __init__(self, samples: list, parent=None):
        super().__init__(parent)
        self._pcts = [s["used"] / s["total"] * 100 for s in samples if s.get("total")]
        self.setFixedHeight(28)
        self.setToolTip(f"{len(self._pcts)} quota samples (last {len(self._pcts)} refreshes)")

    def paintEvent(self, _event):
        if len(self._pcts) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pad = 2
        lo, hi = min(self._pcts), max(self._pcts)
        rng = max(hi - lo, 1.0)

        def pt(i):
            x = pad + (i / (len(self._pcts) - 1)) * (w - 2 * pad)
            y = h - pad - ((self._pcts[i] - lo) / rng) * (h - 2 * pad)
            return QPointF(x, y)

        last_pct = self._pcts[-1]
        if last_pct >= 90:
            color = QColor("#FF453A" if _DARK else "#FF3B30")
        elif last_pct >= 70:
            color = QColor("#FF9F0A" if _DARK else "#FF9500")
        else:
            color = QColor("#0A84FF" if _DARK else "#007AFF")

        poly = QPolygonF([pt(i) for i in range(len(self._pcts))])
        pen = QPen(color, 1.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPolyline(poly)
        p.end()


class StorageTile(QFrame):
    def __init__(self, name, path, exists, on_connect_request=None,
                 provider_override=None, display_account=None, quota_only=False):
        super().__init__()
        self.account_key = name
        self.quota_only = quota_only
        self.provider = provider_override or (cloud_quota.provider_for_name(name) if exists else None)
        self._path = path
        self._exists = exists
        self._worker = None
        self.setFixedWidth(TILE_WIDTH)
        self.setObjectName("StorageTile")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        if provider_override:
            provider = "Google Drive" if provider_override == "google" else "Dropbox"
            account = display_account or ""
        else:
            provider, account = split_tile_name(name)

        top = QHBoxLayout()
        name_lbl = QLabel(provider)
        name_lbl.setObjectName("TileName")
        name_lbl.setToolTip(name)
        top.addWidget(name_lbl)
        top.addStretch()
        dot = "●" if exists else "○"
        status_lbl = QLabel(dot)
        status_lbl.setStyleSheet("color: #16a34a;" if exists else "color: #d1d5db;")
        top.addWidget(status_lbl)
        layout.addLayout(top)

        self.account_lbl = QLabel(account)
        self.account_lbl.setObjectName("TileAccount")
        self.account_lbl.setWordWrap(True)
        self.account_lbl.setToolTip(name)
        # Parent before setVisible. setVisible(True) on a widget that has no
        # parent yet shows it as its own top-level window — a sliver of a window
        # flashing on screen for every tile that has an account line.
        layout.addWidget(self.account_lbl)
        self.account_lbl.setVisible(bool(account))

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)

        self._spark: SparklineWidget | None = None
        self._tile_layout = layout

        self.detail_lbl = QLabel()
        self.detail_lbl.setObjectName("TileFree")
        self.detail_lbl.setWordWrap(True)
        layout.addWidget(self.detail_lbl)

        if path is not None and exists:
            open_btn = link_button("Open in Finder →")
            open_btn.setStyleSheet(open_btn.styleSheet() + "font-size: 10px; padding: 2px 0;")
            open_btn.clicked.connect(lambda: run_cmd(["open", str(path)]))
            layout.addWidget(open_btn)

        if self.provider and exists and not cloud_quota.is_connected(self.account_key):
            connect_btn = link_button("Connect for account quota →")
            connect_btn.setStyleSheet(connect_btn.styleSheet() + "font-size: 10px; padding: 2px 0;")
            if on_connect_request:
                connect_btn.clicked.connect(lambda: on_connect_request(self.account_key, self.provider))
            layout.addWidget(connect_btn)

        self.reconnect_btn = link_button("Token expired — reconnect →")
        self.reconnect_btn.setStyleSheet(self.reconnect_btn.styleSheet() + "font-size: 10px; padding: 2px 0; color: #dc2626;")
        if on_connect_request:
            self.reconnect_btn.clicked.connect(lambda: self._do_reconnect(on_connect_request))
        self.reconnect_btn.setVisible(False)
        layout.addWidget(self.reconnect_btn)

        self.set_usage(path, exists)

    def _do_reconnect(self, on_connect_request):
        cloud_quota.disconnect(self.account_key)
        self.reconnect_btn.setVisible(False)
        self.detail_lbl.setText("Opening browser — sign in and approve access…")
        self._worker = ConnectWorker(self.provider, self.account_key)
        self._worker.done.connect(self._reconnect_done)
        self._worker.start()

    def _reconnect_done(self, ok, err):
        if ok:
            self.detail_lbl.setText("Reconnected!")
            self.set_usage(self._path, self._exists)
        else:
            self.detail_lbl.setText(f"Failed: {err}")
            self.reconnect_btn.setVisible(True)

    def _refresh_sparkline(self):
        samples = _get_quota_history(self.account_key)
        if len(samples) < 3:
            return
        if self._spark is not None:
            self._spark.deleteLater()
        self._spark = SparklineWidget(samples, self)
        # Insert just after the progress bar (index 3 in the tile layout)
        bar_idx = self._tile_layout.indexOf(self.bar)
        self._tile_layout.insertWidget(bar_idx + 1, self._spark)

    def _set_bar(self, pct_used):
        self.bar.setValue(pct_used)
        if pct_used >= 90:
            color = "#FF453A" if _DARK else "#FF3B30"
        elif pct_used >= 70:
            color = "#FF9F0A" if _DARK else "#FF9500"
        else:
            color = "#0A84FF" if _DARK else "#007AFF"
        bar_bg = "#48484A" if _DARK else "#E5E5EA"
        self.bar.setStyleSheet(
            f"QProgressBar {{ border:none; border-radius:4px; background:{bar_bg}; height:6px; }}"
            f"QProgressBar::chunk {{ border-radius:4px; background:{color}; }}"
        )

    def set_usage(self, path, exists):
        if not exists:
            self.bar.setValue(0)
            self.detail_lbl.setText("not mounted")
            return

        if self.provider and cloud_quota.is_connected(self.account_key):
            # Fetch Dropbox email dynamically (mount name doesn't include it)
            if self.provider == "dropbox":
                email = cloud_quota.dropbox_account_email(self.account_key)
                if email:
                    self.account_lbl.setText(email)
                    self.account_lbl.setVisible(True)
            try:
                result = cloud_quota.quota(self.account_key)
                quota_error = None
            except Exception as e:
                result = None
                quota_error = str(e)
            if result is not None:
                used, total = result
                if total:
                    self._set_bar(int(used / total * 100))
                    self.detail_lbl.setText(
                        f"{human_size(used)} used of {human_size(total)}  (account quota)"
                    )
                    _append_quota_sample(self.account_key, used, total)
                    self._refresh_sparkline()
                else:
                    self.bar.setValue(0)
                    self.detail_lbl.setText(f"{human_size(used)} used  (unlimited plan)")
                return
            # Token likely expired or revoked
            expired = quota_error and ("400" in quota_error or "401" in quota_error)
            if expired:
                self.bar.setValue(0)
                self.detail_lbl.setText("")
                self.reconnect_btn.setVisible(True)
                return
            self.detail_lbl.setText(
                "Account quota unavailable" if self.quota_only
                else "Account quota unavailable — showing local disk:"
            )
            if self.quota_only:
                self.bar.setValue(0)
                return

        if self.quota_only:
            self.bar.setValue(0)
            self.detail_lbl.setText("Not connected yet")
            return

        usage = disk_usage_for(path)
        if usage is None:
            self.bar.setValue(0)
            self.detail_lbl.setText("unavailable")
            return
        pct_used = int(usage.used / usage.total * 100) if usage.total else 0
        self._set_bar(pct_used)
        suffix = "  (local disk)" if self.provider else ""
        self.detail_lbl.setText(
            f"{human_size(usage.free)} free of {human_size(usage.total)}{suffix}"
        )


class ICloudTile(QFrame):
    """Storage tile that shows local iCloud cache size via du (no cloud API)."""

    class _Worker(QThread):
        done = Signal(object)  # int bytes or None
        def run(self):
            self.done.emit(icloud_local_bytes())

    def __init__(self):
        super().__init__()
        self.setFixedWidth(TILE_WIDTH)
        self.setObjectName("StorageTile")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        top = QHBoxLayout()
        name_lbl = QLabel("iCloud Drive")
        name_lbl.setObjectName("TileName")
        top.addWidget(name_lbl)
        top.addStretch()
        dot = QLabel("●" if ICLOUD_DIR.exists() else "○")
        dot.setStyleSheet("color: #16a34a;" if ICLOUD_DIR.exists() else "color: #d1d5db;")
        top.addWidget(dot)
        layout.addLayout(top)

        acct_lbl = QLabel("Local cache only")
        acct_lbl.setObjectName("TileAccount")
        layout.addWidget(acct_lbl)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setValue(0)
        layout.addWidget(self.bar)

        self.detail_lbl = QLabel("Calculating…")
        self.detail_lbl.setObjectName("TileFree")
        layout.addWidget(self.detail_lbl)

        note = QLabel("No cloud quota API")
        note.setObjectName("TileAccount")
        layout.addWidget(note)

        open_btn = link_button("Open in Finder →")
        open_btn.setStyleSheet(open_btn.styleSheet() + "font-size: 10px; padding: 2px 0;")
        open_btn.clicked.connect(lambda: run_cmd(["open", str(ICLOUD_DIR)]))
        layout.addWidget(open_btn)

        self._worker = self._Worker()
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, size: int | None):
        bar_bg = "#48484A" if _DARK else "#E5E5EA"
        if size is None:
            self.detail_lbl.setText("Unavailable")
            self.bar.setStyleSheet(
                f"QProgressBar {{ border:none; border-radius:4px; background:{bar_bg}; height:6px; }}"
                f"QProgressBar::chunk {{ border-radius:4px; background:{bar_bg}; }}"
            )
            return
        self.detail_lbl.setText(f"{human_size(size)} local cache")
        # Show bar relative to local disk total so it's meaningful
        usage = disk_usage_for(ICLOUD_DIR)
        if usage and usage.total > 0:
            pct = int(size * 100 / usage.total)
            color = ("#FF453A" if _DARK else "#FF3B30") if pct >= 90 else \
                    ("#FF9F0A" if _DARK else "#FF9500") if pct >= 70 else \
                    ("#0A84FF" if _DARK else "#007AFF")
            self.bar.setValue(pct)
            self.bar.setStyleSheet(
                f"QProgressBar {{ border:none; border-radius:4px; background:{bar_bg}; height:6px; }}"
                f"QProgressBar::chunk {{ border-radius:4px; background:{color}; }}"
            )
        else:
            self.bar.setValue(0)


class FlowLayout(QLayout):
    """Lays widgets out left-to-right, wrapping to a new row when the width runs
    out. The storage tile count is dynamic (mounts + manual accounts + iCloud),
    so a fixed QHBoxLayout clips the rightmost tiles at any window size."""

    def __init__(self, parent=None, spacing=10):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _layout(self, rect, test_only):
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, row_height = eff.x(), eff.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > eff.right() and row_height > 0:
                x = eff.x()
                y = y + row_height + self._spacing
                next_x = x + hint.width() + self._spacing
                row_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            row_height = max(row_height, hint.height())
        return y + row_height - rect.y() + m.bottom()


class StorageCard(Card):
    def __init__(self):
        super().__init__()

        header = QHBoxLayout()
        title_lbl = QLabel("Storage")
        title_lbl.setObjectName("CardTitle")
        header.addWidget(title_lbl)
        header.addStretch()
        add_btn = secondary_button("+ Add account")
        add_btn.clicked.connect(self.open_add_account_dialog)
        header.addWidget(add_btn)
        accounts_btn = secondary_button("☁ Cloud accounts…")
        accounts_btn.clicked.connect(self.open_accounts_dialog)
        header.addWidget(accounts_btn)
        self.vbox.addLayout(header)
        subtitle = QLabel(
            "Local disk free space for every mount, or real account quota once connected")
        subtitle.setObjectName("CardSubtitle")
        self.body(subtitle)

        self.tiles_row = FlowLayout(spacing=10)
        self.body(self.tiles_row)
        self.tiles = []
        self.refresh()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5 * 60 * 1000)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start()

        # Also refresh when network comes back up (catches VPN / wake from sleep).
        if QNetworkInformation.load(QNetworkInformation.Feature.Reachability):
            QNetworkInformation.instance().reachabilityChanged.connect(self._on_net_up)

    def _on_net_up(self, reachability):
        if reachability == QNetworkInformation.Reachability.Online:
            self.refresh()

    def refresh(self):
        # Take each old tile out of the layout, then hide it *before* dropping
        # its parent. setParent(None) on a visible widget makes it a top-level
        # window and Qt leaves it visible: every tile popped out as its own
        # floating 230px panel on screen, which is what a refresh triggered at
        # startup (network reachability, theme change) looked like. hide() first
        # keeps it hidden through the reparent; deleteLater() then disposes of
        # it, which setParent(None) alone never did — the tile's own button
        # lambdas capture the tile, so the reference cycle outlived the refresh.
        while self.tiles_row.count():
            item = self.tiles_row.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.tiles = []
        targets = [t for t in storage_targets() if t[2]]
        mounted_keys = {name for name, _path, _exists in targets}
        for name, path, exists in targets:
            tile = StorageTile(name, path, exists, on_connect_request=self.connect_account)
            self.tiles_row.addWidget(tile)
            self.tiles.append(tile)
        for acc in cloud_quota.load_manual_accounts():
            if acc["key"] in mounted_keys:
                continue
            tile = StorageTile(
                acc["key"], None, True,
                on_connect_request=self.connect_account,
                provider_override=acc["provider"], display_account=acc["label"],
                quota_only=True,
            )
            self.tiles_row.addWidget(tile)
            self.tiles.append(tile)
        # iCloud local cache size (no public API — shows local disk usage only)
        icloud_tile = ICloudTile()
        self.tiles_row.addWidget(icloud_tile)
        self.tiles.append(icloud_tile)

    def open_accounts_dialog(self):
        CloudAccountsDialog(self, on_change=self.refresh).exec()

    def open_add_account_dialog(self):
        AddAccountDialog(self, on_change=self.refresh).exec()

    def connect_account(self, account_key, provider):
        dlg = CloudAccountsDialog(self, on_change=self.refresh)
        dlg.exec()


# ----------------------------------------------------------------------------
# Cloud accounts dialog — OAuth app credentials + per-account connect/disconnect
# ----------------------------------------------------------------------------
class ConnectWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, provider, account_key):
        super().__init__()
        self.provider = provider
        self.account_key = account_key

    def run(self):
        try:
            ok, error = cloud_quota.connect(self.provider, self.account_key)
        except Exception as e:
            ok, error = False, str(e)
        self.done.emit(ok, error or "")


class CloudAccountsDialog(QDialog):
    def __init__(self, parent=None, on_change=None):
        super().__init__(parent)
        self.on_change = on_change
        self.worker = None
        self.setWindowTitle("Cloud Accounts")
        self.resize(560, 460)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Connect Google Drive / Dropbox accounts to show their real storage\n"
            "quota instead of local disk free space. Requires a one-time OAuth app\n"
            "(see README) — paste its Client ID/Secret or App Key/Secret below."
        ))

        creds = cloud_quota.load_app_credentials()
        form = QFormLayout()
        self.google_id = QLineEdit(creds.get("google", {}).get("client_id", ""))
        self.google_secret = QLineEdit(creds.get("google", {}).get("client_secret", ""))
        self.google_secret.setEchoMode(QLineEdit.Password)
        self.dropbox_key = QLineEdit(creds.get("dropbox", {}).get("app_key", ""))
        self.dropbox_secret = QLineEdit(creds.get("dropbox", {}).get("app_secret", ""))
        self.dropbox_secret.setEchoMode(QLineEdit.Password)
        form.addRow("Google Client ID:", self.google_id)
        form.addRow("Google Client Secret:", self.google_secret)
        form.addRow("Dropbox App Key:", self.dropbox_key)
        form.addRow("Dropbox App Secret:", self.dropbox_secret)
        layout.addLayout(form)

        save_btn = secondary_button("Save credentials")
        save_btn.clicked.connect(self.save_credentials)
        layout.addWidget(save_btn)

        layout.addWidget(QLabel("\nAccounts:"))
        self.rows_box = QVBoxLayout()
        layout.addLayout(self.rows_box)
        self.populate_rows()

        layout.addStretch()
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("CardSubtitle")
        layout.addWidget(self.status_lbl)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    def save_credentials(self):
        cloud_quota.save_app_credentials({
            "google": {
                "client_id": self.google_id.text().strip(),
                "client_secret": self.google_secret.text().strip(),
            },
            "dropbox": {
                "app_key": self.dropbox_key.text().strip(),
                "app_secret": self.dropbox_secret.text().strip(),
            },
        })
        self.status_lbl.setText("Saved.")

    def _add_row(self, label_text, name, provider, removable=False):
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        connected = cloud_quota.is_connected(name)
        status = QLabel("● connected" if connected else "○ not connected")
        status.setStyleSheet("color: #16a34a;" if connected else "color: #9ca3af;")
        btn = secondary_button("Disconnect" if connected else "Connect")
        if connected:
            btn.clicked.connect(lambda _, n=name: self.do_disconnect(n))
        else:
            btn.clicked.connect(lambda _, n=name, p=provider: self.do_connect(n, p))
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(status)
        row.addWidget(btn)
        if removable:
            rm_btn = secondary_button("Remove")
            rm_btn.clicked.connect(lambda _, n=name: self.do_remove(n))
            row.addWidget(rm_btn)
        w = QWidget()
        w.setLayout(row)
        self.rows_box.addWidget(w)

    def populate_rows(self):
        while self.rows_box.count():
            item = self.rows_box.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Deduplicate by base email (same logic as storage_targets)
        seen = {}
        for name, _path, exists in cloud_services():
            if not exists:
                continue
            p = cloud_quota.provider_for_name(name)
            if not p:
                continue
            _, account = split_tile_name(name)
            base = re.sub(r'\s+\(\d{2}-\d{2}-\d{4}.*\)$', '', account).strip()
            key = (p, base)
            if key not in seen or len(name) < len(seen[key][0]):
                seen[key] = (name, p)
        mounted = list(seen.values())
        manual = cloud_quota.load_manual_accounts()

        if not mounted and not manual:
            self.rows_box.addWidget(QLabel("No Google Drive / Dropbox mounts or added accounts found."))
            return

        if mounted:
            self.rows_box.addWidget(QLabel("Mounted folders:"))
            for name, provider in mounted:
                self._add_row(name, name, provider)

        if manual:
            self.rows_box.addWidget(QLabel("Added accounts:"))
            for acc in manual:
                self._add_row(acc["label"], acc["key"], acc["provider"], removable=True)

    def do_remove(self, account_key):
        cloud_quota.remove_manual_account(account_key)
        self.populate_rows()
        if self.on_change:
            self.on_change()

    def do_connect(self, account_key, provider):
        self.status_lbl.setText(f"Opening browser to connect {account_key} — sign in and approve access…")
        self.worker = ConnectWorker(provider, account_key)
        self.worker.done.connect(self._connect_finished)
        self.worker.start()

    def _connect_finished(self, ok, error):
        if ok:
            self.status_lbl.setText("Connected.")
        else:
            self.status_lbl.setText(f"Failed: {error}")
        self.populate_rows()
        if self.on_change:
            self.on_change()

    def do_disconnect(self, account_key):
        cloud_quota.disconnect(account_key)
        self.populate_rows()
        if self.on_change:
            self.on_change()


class AddAccountDialog(QDialog):
    """Add a Google Drive / Dropbox account to monitor, with no local mount required."""

    def __init__(self, parent=None, on_change=None):
        super().__init__(parent)
        self.on_change = on_change
        self.worker = None
        self.setWindowTitle("Add Account")
        self.resize(420, 220)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Monitor a Google Drive or Dropbox account's storage quota even if it\n"
            "isn't mounted locally. Needs the OAuth app credentials from\n"
            "Cloud Accounts… saved first."
        ))

        form = QFormLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("Google Drive", "google")
        self.provider_combo.addItem("Dropbox", "dropbox")
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("e.g. work.account@gmail.com")
        form.addRow("Provider:", self.provider_combo)
        form.addRow("Label:", self.label_edit)
        layout.addLayout(form)

        layout.addStretch()
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("CardSubtitle")
        layout.addWidget(self.status_lbl)

        row = QHBoxLayout()
        row.addStretch()
        cancel_btn = secondary_button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        connect_btn = QPushButton("Connect…")
        connect_btn.clicked.connect(self.do_connect)
        row.addWidget(cancel_btn)
        row.addWidget(connect_btn)
        layout.addLayout(row)

    def do_connect(self):
        label = self.label_edit.text().strip()
        provider = self.provider_combo.currentData()
        if not label:
            self.status_lbl.setText("Enter a label for this account first.")
            return
        key = f"{provider}:{label}"
        existing = [a["key"] for a in cloud_quota.load_manual_accounts()]
        if key in existing or cloud_quota.is_connected(key):
            self.status_lbl.setText("An account with that label already exists.")
            return

        self.status_lbl.setText("Opening browser — sign in and approve access…")
        self.worker = ConnectWorker(provider, key)
        self.worker.done.connect(lambda ok, err: self._finished(ok, err, key, provider, label))
        self.worker.start()

    def _finished(self, ok, error, key, provider, label):
        if not ok:
            self.status_lbl.setText(f"Failed: {error}")
            return
        cloud_quota.add_manual_account(key, provider, label)
        if self.on_change:
            self.on_change()
        self.accept()


# ----------------------------------------------------------------------------
# Excludes editor dialog
# ----------------------------------------------------------------------------
class ExcludesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit backup excludes")
        self.resize(560, 480)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Patterns skipped during backup (rsync --exclude-from):"))
        self.edit = QPlainTextEdit()
        if EXCLUDES_FILE.exists():
            self.edit.setPlainText(EXCLUDES_FILE.read_text())
        layout.addWidget(self.edit)
        row = QHBoxLayout()
        preview_btn = secondary_button("🔍 Preview matches")
        preview_btn.clicked.connect(self.preview_matches)
        save = QPushButton("Save")
        save.clicked.connect(self.save)
        cancel = secondary_button("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(preview_btn)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(save)
        layout.addLayout(row)

    def save(self):
        EXCLUDES_FILE.write_text(self.edit.toPlainText())
        self.accept()

    def preview_matches(self):
        patterns = [l.strip() for l in self.edit.toPlainText().splitlines()
                    if l.strip() and not l.startswith("#")]
        if not patterns:
            QMessageBox.information(self, "No patterns", "No exclude patterns to preview.")
            return
        folders = read_folders()[:3]
        matches = []
        for folder in folders:
            src = str(DOCS / folder)
            for pat in patterns[:15]:
                rc, out, _ = run_cmd(
                    ["find", src, "-name", pat, "-maxdepth", "6"], timeout=10)
                for line in (out.strip().splitlines() or []):
                    matches.append(line)
                    if len(matches) >= 200:
                        break
                if len(matches) >= 200:
                    break
        dlg = QDialog(self)
        dlg.setWindowTitle("Exclude pattern matches")
        dlg.resize(700, 420)
        v = QVBoxLayout(dlg)
        note = f"{len(matches)} paths matched across first {len(folders)} folder(s)" + \
               (" (truncated)" if len(matches) >= 200 else "")
        v.addWidget(QLabel(note if matches else "No matches found in the first 3 backed-up folders."))
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText("\n".join(matches) or "(no matches)")
        v.addWidget(viewer)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton("Close")
        ok.clicked.connect(dlg.accept)
        btn_row.addWidget(ok)
        v.addLayout(btn_row)
        dlg.exec()


# ----------------------------------------------------------------------------
# Backup history dialog
# ----------------------------------------------------------------------------
class BackupHistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Backup History")
        self.resize(720, 380)
        layout = QVBoxLayout(self)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Date", "Started", "Duration", "Transferred", "Status"])
        hdr = self._table.horizontalHeader()
        for c in range(4):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)

        self._runs = self._parse_runs()
        self._table.setRowCount(len(self._runs))
        for r, (date, started, duration, transferred, status, _log_path) in enumerate(self._runs):
            for c, val in enumerate([date, started, duration, transferred, status]):
                item = QTableWidgetItem(val)
                if c == 4:
                    item.setForeground(
                        QColor("#16a34a") if val == "OK"
                        else QColor("#dc2626") if val == "ERRORS"
                        else QColor("#9ca3af")
                    )
                self._table.setItem(r, c, item)

        layout.addWidget(self._table)

        row = QHBoxLayout()
        self._view_btn = secondary_button("📄 View log")
        self._view_btn.clicked.connect(self._view_log)
        row.addWidget(self._view_btn)
        row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def _view_log(self):
        rows = self._table.selectedItems()
        if not rows:
            return
        r = self._table.currentRow()
        if r < 0 or r >= len(self._runs):
            return
        log_path = self._runs[r][5]
        if not log_path or not Path(log_path).exists():
            QMessageBox.information(self, "Log not found", f"Log file not found:\n{log_path}")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Log — {Path(log_path).name}")
        dlg.resize(800, 600)
        v = QVBoxLayout(dlg)
        viewer = QPlainTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(Path(log_path).read_text(errors="replace"))
        viewer.moveCursor(QTextCursor.End)
        v.addWidget(viewer)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton("Close")
        ok.clicked.connect(dlg.accept)
        btn_row.addWidget(ok)
        v.addLayout(btn_row)
        dlg.exec()

    def _parse_runs(self):
        """The last 15 runs, newest first — runs, not days.

        Several backups a day share one log file, so iterating files listed only
        each day's first run and hid the rest.
        """
        runs = []
        for log_path in sorted(glob.glob(str(LOG_DIR / "backup_*.log")), reverse=True):
            text = Path(log_path).read_text(errors="replace")
            for date, started, block in reversed(list(iter_log_runs(text))):
                duration = "—"
                finished = run_finished_at(block)
                if finished:
                    try:
                        t0 = datetime.strptime(f"{date} {started}", "%Y-%m-%d %H:%M:%S")
                        t1 = datetime.strptime(finished, "%Y-%m-%d %H:%M:%S")
                        secs = int((t1 - t0).total_seconds())
                        duration = f"{secs // 60}m {secs % 60}s"
                    except ValueError:
                        pass
                # One rsync invocation per folder, so a run has several totals.
                total = 0
                for m in re.finditer(
                        r"Total transferred file size:\s*([\d,]+)\s*bytes", block):
                    try:
                        total += int(m.group(1).replace(",", ""))
                    except ValueError:
                        pass
                transferred = human_size(total) if total else "—"
                runs.append((date, started, duration, transferred,
                             run_status(block), log_path))
                if len(runs) >= 15:
                    return runs
        return runs


# ----------------------------------------------------------------------------
# Backup status & schedule card
# ----------------------------------------------------------------------------
class BackupStatusCard(Card):
    def __init__(self):
        super().__init__("Google Drive Backup", "Status, schedule, and manual run")
        self.proc = None
        self._dry_run = False
        self._paused = False
        self._last_overdue_notify: datetime | None = load_overdue_stamp()

        info, _ = last_backup_info()
        self.status_lbl = QLabel(info)
        self.body(self.status_lbl)

        sched = QHBoxLayout()
        self.sched_lbl = QLabel()
        self.sched_btn = secondary_button("")
        self.sched_btn.clicked.connect(self.toggle_schedule)
        sched.addWidget(self.sched_lbl)
        sched.addStretch()
        sched.addWidget(self.sched_btn)
        self.body(sched)

        wake = QHBoxLayout()
        self.wake_lbl = QLabel()
        self.wake_btn = secondary_button("")
        self.wake_btn.clicked.connect(self.toggle_wake)
        wake.addWidget(self.wake_lbl)
        wake.addStretch()
        wake.addWidget(self.wake_btn)
        self.body(wake)

        login = QHBoxLayout()
        self.login_lbl = QLabel()
        self.login_btn = secondary_button("")
        self.login_btn.clicked.connect(self.toggle_login_item)
        login.addWidget(self.login_lbl)
        login.addStretch()
        login.addWidget(self.login_btn)
        self.body(login)

        runrow = QHBoxLayout()
        self.run_btn = QPushButton("▶  Run backup now")
        self.run_btn.clicked.connect(self.run_backup)
        self.dry_btn = secondary_button("⚟  Dry run")
        self.dry_btn.clicked.connect(self.run_dry_run)
        self.preview_del_btn = secondary_button("🗑  Preview deletions")
        self.preview_del_btn.setToolTip(
            "List what mirroring would remove from Google Drive. Changes nothing.")
        self.preview_del_btn.clicked.connect(self.run_delete_preview)
        self.pause_btn = secondary_button("⏸  Pause")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.setEnabled(False)
        self.stop_btn = secondary_button("■  Stop")
        self.stop_btn.setProperty("danger", True)
        self.stop_btn.clicked.connect(self.stop_backup)
        self.stop_btn.setEnabled(False)
        self.history_btn = secondary_button("📋 History")
        self.history_btn.clicked.connect(lambda: BackupHistoryDialog(self).exec())
        runrow.addWidget(self.run_btn)
        runrow.addWidget(self.dry_btn)
        runrow.addWidget(self.preview_del_btn)
        runrow.addWidget(self.pause_btn)
        runrow.addWidget(self.stop_btn)
        runrow.addStretch()
        runrow.addWidget(self.history_btn)
        self.body(runrow)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(140)
        self.body(self.log)
        self._preload_log()

        self.refresh_schedule()
        self.refresh_wake()
        self.refresh_login_item()

        # Poll every 5 min so auto-backup fires shortly after 03:30 on wake.
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(5 * 60 * 1000)
        self._auto_timer.timeout.connect(self._maybe_auto_backup)
        self._auto_timer.start()
        # Also check immediately in case the app was just opened after a missed night.
        QTimer.singleShot(10_000, self._maybe_auto_backup)

        # Network-triggered backup: fire ~30 s after the Mac comes back online.
        _net_ok = QNetworkInformation.load(QNetworkInformation.Feature.Reachability)
        if _net_ok:
            net = QNetworkInformation.instance()
            net.reachabilityChanged.connect(self._on_reachability_changed)
        net_lbl = QLabel("🌐 Network trigger: " + ("active" if _net_ok else "unavailable"))
        net_lbl.setObjectName("CardSubtitle")
        self.body(net_lbl)

        # USB mount trigger: backup when a new volume appears in /Volumes.
        self._known_volumes = set(os.listdir("/Volumes"))
        self._vol_watcher = QFileSystemWatcher(["/Volumes"], self)
        self._vol_watcher.directoryChanged.connect(self._on_volumes_changed)

    def _maybe_auto_backup(self):
        """Run the backup automatically if the schedule is on, it's past the configured
        time, and no backup has run since that time today. Also notifies if >25 h overdue."""
        if self.proc is not None:
            return  # already running
        st = _load_state()
        bk_h, bk_m = st.get("backup_hour", 3), st.get("backup_minute", 30)

        if not launchd_loaded():
            age = last_backup_age_hours()
            if age is not None and age > 25:
                self._notify_overdue(
                    f"Last backup was {int(age)}h ago — schedule is disabled."
                )
            return

        now = datetime.now()
        if now.hour < bk_h or (now.hour == bk_h and now.minute < bk_m):
            age = last_backup_age_hours()
            if age is not None and age > 25:
                self._notify_overdue(f"Last successful backup was {int(age)}h ago.")
            return

        today_log = LOG_DIR / f"backup_{now.date()}.log"
        if today_log.exists():
            text = today_log.read_text(errors="replace")
            for m in re.finditer(
                r"\[(\d{4}-\d{2}-\d{2} (\d{2}):(\d{2}):\d{2})\] ===== Backup run started", text
            ):
                h, mi = int(m.group(2)), int(m.group(3))
                if h > bk_h or (h == bk_h and mi >= bk_m):
                    return  # already ran today after the scheduled time
        self.run_backup()

    def _notify_overdue(self, message: str) -> None:
        """Send an overdue-backup notification at most once per hour, persisted across restarts."""
        now = datetime.now()
        if not overdue_notice_due(self._last_overdue_notify, now):
            return
        self._last_overdue_notify = now
        save_overdue_stamp(now)
        _notify("Backup Control Center", message, "Backup overdue")

    def _preload_log(self) -> None:
        """Show the tail of the most recent backup log at startup, restoring scroll position."""
        logs = sorted(glob.glob(str(LOG_DIR / "backup_*.log")))
        if not logs:
            return
        try:
            text = Path(logs[-1]).read_text(errors="replace")
        except OSError:
            return
        tail = "\n".join(text.splitlines()[-60:])
        self.log.setPlainText(tail)
        saved_pos = _load_state().get("log_scroll_pos", -1)
        if saved_pos >= 0:
            self.log.verticalScrollBar().setValue(saved_pos)
        else:
            self.log.moveCursor(QTextCursor.End)

    def save_log_scroll(self) -> None:
        state = _load_state()
        state["log_scroll_pos"] = self.log.verticalScrollBar().value()
        _save_state(state)

    def _on_reachability_changed(self, reachability):
        if reachability == QNetworkInformation.Reachability.Online:
            # Wait 30 s for Google Drive to mount before attempting backup.
            QTimer.singleShot(30_000, self._backup_on_network_up)

    def _backup_on_network_up(self):
        """Run backup when Mac comes online if no successful backup in the past 12 h."""
        if self.proc is not None:
            return
        if not launchd_loaded():
            return
        age = last_backup_age_hours()
        if age is None or age > 12:
            self.run_backup()

    def _on_volumes_changed(self, _path):
        current = set(os.listdir("/Volumes"))
        new_vols = current - self._known_volumes
        self._known_volumes = current
        if new_vols and launchd_loaded():
            # New USB drive mounted — back up after 10 s if overdue by >6 h.
            QTimer.singleShot(10_000, self._backup_on_usb_mount)

    def _backup_on_usb_mount(self):
        if self.proc is not None:
            return
        age = last_backup_age_hours()
        if age is None or age > 6:
            self.run_backup()

    def run_single_folder(self, folder: str):
        """Run rsync for one folder only (triggered from Folders card right-click)."""
        if self.proc is not None:
            QMessageBox.information(self, "Busy", "Stop the running backup before starting a new one.")
            return
        if not DRIVE_ROOT.exists():
            self.status_lbl.setText("⚠ Google Drive not mounted — cannot run backup.")
            return
        src = str(DOCS / folder) + "/"
        dest = str(DEST_ROOT / folder) + "/"
        self._dry_run = False
        self._paused = False
        self.log.clear()
        self.log.insertPlainText(f"=== Quick backup: {folder} ===\n\n")
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read_output)
        self.proc.finished.connect(self._finished)
        self.run_btn.setEnabled(False)
        self.dry_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.proc.start("/opt/homebrew/bin/rsync", [
            "-rltvh", "--update", "--modify-window=2",
            "--no-perms", "--no-owner", "--no-group",
            f"--exclude-from={EXCLUDES_FILE}",
            "--stats", "--itemize-changes",
            src, dest,
        ])

    def refresh_status(self):
        info, _ = last_backup_info()
        self.status_lbl.setText(info)

    def refresh_schedule(self):
        loaded = launchd_loaded()
        st = _load_state()
        bk_h, bk_m = st.get("backup_hour", 3), st.get("backup_minute", 30)
        time_str = f"{bk_h:02d}:{bk_m:02d}"
        self.sched_lbl.setText(
            f"🕒 Nightly schedule ({time_str}): " + ("ENABLED" if loaded else "disabled"))
        self.sched_btn.setText("Disable" if loaded else "Enable")

    def _wanted_wake(self):
        st = _load_state()
        return wake_time_for_backup(st.get("backup_hour", 3), st.get("backup_minute", 30))

    def refresh_wake(self):
        current = current_wake_schedule()
        wake_h, wake_m = self._wanted_wake()
        label = f"⏰ Wake Mac at {wake_h:02d}:{wake_m:02d} for backup: "
        if current is None:
            self.wake_lbl.setText(label + "disabled")
            self.wake_btn.setText("Enable")
        elif current == (wake_h, wake_m):
            self.wake_lbl.setText(label + "ENABLED")
            self.wake_btn.setText("Disable")
        else:
            # The backup time was changed in Settings after the wake was set.
            self.wake_lbl.setText(label + f"set for {current[0]:02d}:{current[1]:02d} instead")
            self.wake_btn.setText("Update")

    def refresh_login_item(self):
        is_item = is_login_item()
        self.login_lbl.setText("🚀 Open at login (menu bar only): "
                               + ("ENABLED" if is_item else "disabled"))
        self.login_btn.setText("Disable" if is_item else "Enable")

    def toggle_login_item(self):
        is_item = is_login_item()
        ok, err = set_login_item(not is_item)
        if not ok and err and "User cancelled" not in err:
            QMessageBox.warning(self, "Login Item", f"Could not change login item:\n{err}")
        self.refresh_login_item()

    def toggle_wake(self):
        wanted = self._wanted_wake()
        if current_wake_schedule() == wanted:
            ok, err = set_wake_schedule(False)
        else:
            ok, err = set_wake_schedule(True, *wanted)
        if not ok:
            if err and "User cancelled" not in err:
                QMessageBox.warning(self, "Wake schedule", f"Could not update wake schedule:\n{err}")
        self.refresh_wake()

    def toggle_schedule(self):
        if launchd_loaded():
            run_cmd(["launchctl", "unload", str(PLIST_DST)], timeout=15)
        else:
            if not PLIST_SRC.exists():
                QMessageBox.warning(self, "Missing plist", f"Not found:\n{PLIST_SRC}")
                return
            PLIST_DST.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(str(PLIST_SRC), str(PLIST_DST))
            run_cmd(["launchctl", "load", str(PLIST_DST)], timeout=15)
        self.refresh_schedule()

    def run_backup(self):
        if self.proc is not None:
            return
        if not DRIVE_ROOT.exists():
            self.status_lbl.setText("⚠ Google Drive not mounted — cannot run backup.")
            return
        self._dry_run = False
        self.log.clear()
        self.proc = QProcess(self)
        if _load_state().get("mirror_mode", False):
            env = QProcessEnvironment.systemEnvironment()
            env.insert("MIRROR", "1")
            self.proc.setProcessEnvironment(env)
            self.log.insertPlainText(
                "=== MIRROR MODE ON — files deleted locally are removed from Drive "
                "(archived under _deleted/) ===\n\n")
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read_output)
        self.proc.finished.connect(self._finished)
        self.run_btn.setEnabled(False)
        self.dry_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.proc.start("/bin/bash", [str(SCRIPT)])

    def run_dry_run(self):
        if self.proc is not None:
            QMessageBox.information(self, "Busy",
                                    "Stop the running backup before starting a dry run.")
            return
        self._dry_run = True
        self.log.clear()
        self.log.insertPlainText("=== DRY RUN — no files will be changed ===\n\n")
        self.proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("DRY_RUN", "1")
        self.proc.setProcessEnvironment(env)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read_output)
        self.proc.finished.connect(self._finished)
        self.run_btn.setEnabled(False)
        self.dry_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.proc.start("/bin/bash", [str(SCRIPT)])

    def run_delete_preview(self):
        """List what mirror mode would delete from Drive. Changes nothing.

        DRY_RUN=1 MIRROR=1 is the script's own preview combination, so this
        shows exactly what enabling mirroring would do, not an approximation.
        """
        if self.proc is not None:
            QMessageBox.information(self, "Busy",
                                    "Stop the running backup before previewing deletions.")
            return
        if not DRIVE_ROOT.exists():
            self.status_lbl.setText("⚠ Google Drive not mounted — cannot preview.")
            return
        self._dry_run = True  # writes to dryrun_*.log, so it can't look like a real run
        self.log.clear()
        self.log.insertPlainText(
            "=== DELETION PREVIEW — nothing will be changed ===\n"
            "Lines marked '*deleting' are what mirror mode would remove from Drive.\n\n")
        self.proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("DRY_RUN", "1")
        env.insert("MIRROR", "1")
        self.proc.setProcessEnvironment(env)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read_output)
        self.proc.finished.connect(self._delete_preview_finished)
        self.run_btn.setEnabled(False)
        self.dry_btn.setEnabled(False)
        self.preview_del_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.proc.start("/bin/bash", [str(SCRIPT)])

    def _delete_preview_finished(self):
        # rsync --itemize-changes marks removals "*deleting   <path>", with the
        # asterisk; a plain "deleting" prefix never matches. Paths ending in "/"
        # are the directories left behind once their contents go, counted apart
        # so the headline number is files.
        files = dirs = 0
        for ln in self.log.toPlainText().splitlines():
            s = ln.strip()
            if not s.startswith("*deleting"):
                continue
            path = s[len("*deleting"):].strip()
            if path.endswith("/"):
                dirs += 1
            else:
                files += 1
        self._finished()
        self.preview_del_btn.setEnabled(True)
        if files or dirs:
            extra = f" and {dirs} empty folder(s)" if dirs else ""
            self.log.appendPlainText(
                f"\n=== {files} file(s){extra} would be removed from Drive.\n"
                "Copies would be kept under Backups/MacBook/_deleted/<date>/.\n"
                "Turn on mirror mode in Settings to apply this. ===")
        else:
            self.log.appendPlainText(
                "\n=== Nothing to delete — the backup already matches your Mac. ===")

    def toggle_pause(self):
        if self.proc is None:
            return
        pid = self.proc.processId()
        if not self._paused:
            os.kill(pid, _signal.SIGSTOP)
            self._paused = True
            self.pause_btn.setText("▶  Resume")
        else:
            os.kill(pid, _signal.SIGCONT)
            self._paused = False
            self.pause_btn.setText("⏸  Pause")

    def stop_backup(self):
        if self.proc is not None:
            if self._paused:
                os.kill(self.proc.processId(), _signal.SIGCONT)
                self._paused = False
            self.proc.kill()

    def _read_output(self):
        data = self.proc.readAllStandardOutput().data().decode("utf-8", "replace")
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log.setTextCursor(cursor)
        self.log.insertPlainText(data)

    def _fire_webhook(self, message: str):
        url = _load_state().get("webhook_url", "").strip()
        if not url:
            return
        payload = json.dumps({"text": message, "message": message}).encode()

        class _WebhookThread(QThread):
            def __init__(self, url, payload):
                super().__init__()
                self._url, self._payload = url, payload

            def run(self):
                try:
                    req = urllib.request.Request(
                        self._url, data=self._payload,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    urllib.request.urlopen(req, timeout=15)
                except Exception:
                    pass

        t = _WebhookThread(url, payload)
        t.finished.connect(t.deleteLater)
        t.start()

    def _finished(self):
        was_dry = self._dry_run
        self._dry_run = False
        self._paused = False
        self.run_btn.setEnabled(True)
        self.dry_btn.setEnabled(True)
        self.preview_del_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("⏸  Pause")
        self.stop_btn.setEnabled(False)
        self.proc = None
        self.refresh_status()
        if not was_dry:
            info, _ = last_backup_info()
            if "OK" in info:
                _notify("Backup Control Center", "Backup completed successfully.", "Google Drive Backup")
            elif "ERRORS" in info:
                _notify("Backup Control Center", "Backup finished with errors — check the log.", "Google Drive Backup")
                self._fire_webhook("Backup Control Center: backup finished WITH ERRORS. Check the log.")


# ----------------------------------------------------------------------------
# Backed-up folders card
# ----------------------------------------------------------------------------
class FoldersCard(Card):
    single_backup_requested = Signal(str)  # folder name

    def __init__(self):
        super().__init__("Backed-up Folders", "What gets rsync'd to Google Drive")
        # A table, not a list of "name — last synced: …" strings: the dates
        # only line up when they sit in a column of their own.
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Folder", "Last synced", "Size"])
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.horizontalHeaderItem(2).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.columns = ResizableColumns(self.table, "folders", self._fit_columns)
        self.table.setToolTip("Double-click a folder to open it in Finder")
        self.table.cellDoubleClicked.connect(lambda r, _c: self._open_folder(self._folder_at(r)))
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setTextElideMode(Qt.ElideMiddle)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._folder_context_menu)
        self.body(self.table)

        row = QHBoxLayout()
        add = secondary_button("➕ Add folder")
        add.clicked.connect(self.add_folder)
        rem = secondary_button("➖ Remove selected")
        rem.clicked.connect(self.remove_folder)
        exc = secondary_button("✎ Edit excludes")
        exc.clicked.connect(self.edit_excludes)
        row.addWidget(add)
        row.addWidget(rem)
        row.addWidget(exc)
        row.addStretch()
        self.body(row)

        self.total_lbl = QLabel("Backup set size: calculating…")
        self.total_lbl.setObjectName("CardSubtitle")
        self.body(self.total_lbl)

        self.reload_folders()

    def reload_folders(self):
        sync_times = last_sync_per_folder()
        folders = read_folders()
        self.table.setRowCount(len(folders))
        for r, f in enumerate(folders):
            name = QTableWidgetItem(str(DOCS / f))
            name.setData(Qt.UserRole, f)
            self.table.setItem(r, 0, name)
            last = sync_times.get(f)
            synced = QTableWidgetItem(last[:16] if last else "never synced")
            if not last:
                synced.setForeground(QColor("#d97706"))
            self.table.setItem(r, 1, synced)
            size = QTableWidgetItem("…")
            size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, 2, size)
        fit_height_to_rows(self.table)
        self.columns.fit()
        self.total_lbl.setText("Backup set size: calculating…")
        worker = SizeWorker(folders)
        worker.done.connect(self._show_sizes)
        self.worker = replace_worker(getattr(self, "worker", None), worker)

    def _show_sizes(self, sizes, total):
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 2)
            if item is not None:
                item.setText(sizes.get(self._folder_at(r), "?"))
        self.columns.fit()
        self.total_lbl.setText(f"Backup set size (local originals): {total}")

    def _fit_columns(self):
        # Date and size take what they need; the path gets the rest of the row.
        t = self.table
        t.resizeColumnToContents(1)
        # Not resizeColumnToContents(2): the last column is stretched to the
        # table's edge, so its current width is not what it needs.
        size_w = max(t.sizeHintForColumn(2), t.horizontalHeader().sectionSizeHint(2))
        rest = t.viewport().width() - t.columnWidth(1) - size_w
        t.setColumnWidth(0, max(rest, 200))

    @staticmethod
    def _open_folder(folder):
        if folder:
            run_cmd(["open", str(DOCS / folder)])

    def _folder_at(self, row):
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item is not None else None

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Pick a folder under Documents", str(DOCS))
        if not d:
            return
        try:
            rel = Path(d).resolve().relative_to(DOCS.resolve())
        except ValueError:
            QMessageBox.warning(self, "Outside Documents",
                                 "Please pick a folder inside ~/Documents.")
            return
        folders = read_folders()
        rel = str(rel)
        if rel in folders:
            return
        folders.append(rel)
        write_folders(folders)
        self.reload_folders()

    def remove_folder(self):
        folder_name = self._folder_at(self.table.currentRow())
        if not folder_name:
            return
        answer = QMessageBox.question(
            self, "Remove folder",
            f'Remove "{folder_name}" from the backup?\n\nFiles already in Google Drive are not deleted.',
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        folders = [f for f in read_folders() if f != folder_name]
        write_folders(folders)
        self.reload_folders()

    def _folder_context_menu(self, pos):
        folder = self._folder_at(self.table.rowAt(pos.y()))
        if not folder:
            return
        menu = QMenu(self)
        open_action = menu.addAction("📂 Open in Finder")
        backup_action = menu.addAction(f"▶ Back up '{folder}' now")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == open_action:
            self._open_folder(folder)
        elif action == backup_action:
            self.single_backup_requested.emit(folder)

    def edit_excludes(self):
        ExcludesDialog(self).exec()


class LabHealthCard(Card):
    def __init__(self):
        super().__init__("Lab Health", "Disk usage, git status, and reclaimable space per active project")
        self.summary_lbl = QLabel("Scanning…")
        self.summary_lbl.setObjectName("CardSubtitle")
        self.body(self.summary_lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["", "Project", "Total", "Reclaimable", "Git", "Manifest / .env"])
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.columns = ResizableColumns(
            self.table, "lab_health",
            lambda: [self.table.resizeColumnToContents(c) for c in range(5)])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.body(self.table)

        row = QHBoxLayout()
        rescan = secondary_button("🔄 Rescan")
        rescan.clicked.connect(self.rescan)
        clean = secondary_button("🧹 Clean up checked")
        clean.clicked.connect(self.clean_checked)
        row.addWidget(rescan)
        row.addWidget(clean)
        row.addStretch()
        self.body(row)

        hint = QLabel(
            "Reclaimable = .venv, build, dist, __pycache__ and similar — git-ignored, "
            "excluded from the Drive backup, and rebuildable with uv sync / pip install.")
        hint.setObjectName("CardSubtitle")
        hint.setWordWrap(True)
        self.body(hint)

        self._rows = []
        self.rescan()

    def rescan(self):
        self.summary_lbl.setText("Scanning…")
        worker = LabHealthWorker()
        worker.done.connect(self._populate)
        self.worker = replace_worker(getattr(self, "worker", None), worker)

    def _populate(self, rows):
        self._rows = rows
        self.table.setRowCount(len(rows))
        total_reclaim_kb = 0

        for r, row in enumerate(rows):
            chk = QTableWidgetItem()
            if row["reclaim_kb"] > 0:
                chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                chk.setCheckState(Qt.Checked)
            else:
                chk.setFlags(Qt.NoItemFlags)
            self.table.setItem(r, 0, chk)

            self.table.setItem(r, 1, QTableWidgetItem(row["name"]))
            self.table.setItem(r, 2, QTableWidgetItem(human_size(row["total_kb"] * 1024)))
            self.table.setItem(
                r, 3, QTableWidgetItem(
                    human_size(row["reclaim_kb"] * 1024) if row["reclaim_kb"] else "—"))
            total_reclaim_kb += row["reclaim_kb"]

            if not row["has_git"]:
                git_text, git_color = "no git repo", "#dc2626"
            elif row["uncommitted"]:
                git_text, git_color = f"{row['uncommitted']} uncommitted", "#d97706"
            else:
                git_text, git_color = f"clean ({row['last_commit']})", "#16a34a"
            git_item = QTableWidgetItem(git_text)
            git_item.setForeground(QColor(git_color))
            self.table.setItem(r, 4, git_item)

            notes = [] if row["has_manifest"] else ["⚠️ no requirements.txt / pyproject.toml"]
            if row["env_flag"]:
                notes.append(row["env_flag"])
            notes_item = QTableWidgetItem("; ".join(notes) if notes else "—")
            if notes:
                notes_item.setForeground(QColor("#d97706"))
            self.table.setItem(r, 5, notes_item)
        fit_height_to_rows(self.table)
        self.columns.fit()

        n_reclaim = sum(1 for row in rows if row["reclaim_kb"] > 0)
        self.summary_lbl.setText(
            f"{human_size(total_reclaim_kb * 1024)} reclaimable across {n_reclaim} of "
            f"{len(rows)} projects"
        )

    def _context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0 or row >= len(self._rows):
            return
        project_path = LAB_ACTIVE / self._rows[row]["name"]
        menu = QMenu(self)
        open_action = menu.addAction("📂 Open in Finder")
        term_action = menu.addAction("🖥 Open in Terminal")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == open_action:
            subprocess.run(["open", str(project_path)])
        elif action == term_action:
            subprocess.run(["open", "-a", "Terminal", str(project_path)])

    def clean_checked(self):
        targets = []  # (project_name, path, kb)
        for r, row in enumerate(self._rows):
            item = self.table.item(r, 0)
            if item and item.flags() & Qt.ItemIsUserCheckable and item.checkState() == Qt.Checked:
                for p, kb in row["reclaim_items"]:
                    targets.append((row["name"], p, kb))

        if not targets:
            QMessageBox.information(
                self, "Nothing to clean", "No checked projects have reclaimable space.")
            return

        total_kb = sum(kb for _, _, kb in targets)
        listing = "\n".join(f"  {name}/{p.name}  ({human_size(kb * 1024)})"
                             for name, p, kb in targets[:20])
        if len(targets) > 20:
            listing += f"\n  … and {len(targets) - 20} more"
        answer = QMessageBox.question(
            self, "Clean up disposable folders",
            f"Delete these {len(targets)} folders, reclaiming "
            f"{human_size(total_kb * 1024)}?\n\n{listing}\n\n"
            "These are git-ignored and excluded from the Drive backup — rebuild with "
            "uv sync / pip install -r requirements.txt when you next need them.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return

        errors = []
        for name, p, _ in targets:
            try:
                shutil.rmtree(p)
            except Exception as e:
                errors.append(f"{name}/{p.name}: {e}")
        if errors:
            QMessageBox.warning(self, "Some deletions failed", "\n".join(errors))
        self.rescan()


# ----------------------------------------------------------------------------
# Time Machine card
# ----------------------------------------------------------------------------
TM_SETTINGS_URL = "x-apple.systempreferences:com.apple.Time-Machine-Settings.extension"


def _read_plist(text):
    try:
        data = plistlib.loads(text.encode())
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def tm_has_destination(destinationinfo_xml):
    """`tmutil destinationinfo -X` -> whether any backup disk is configured.

    Unparseable output counts as configured: better to offer a backup that
    fails visibly than to claim Time Machine is off when we just can't tell.
    """
    data = _read_plist(destinationinfo_xml)
    if data is None:
        return True
    return bool(data.get("Destinations"))


def parse_tm_status(status_xml):
    """`tmutil status -X` -> (running, phase, percent 0-100 or None).

    Read the plist, never the text form: the text form prints `Running = 0;`
    when idle, so looking for the word "Running" reports a backup forever.
    """
    data = _read_plist(status_xml) or {}
    running = bool(data.get("Running"))
    if not running:
        return False, None, None
    phase = data.get("BackupPhase")
    pct = (data.get("Progress") or {}).get("Percent", data.get("Percent"))
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        pct = None
    percent = round(pct * 100) if pct is not None and 0 <= pct <= 1 else None
    return True, phase, percent


def describe_tm_latest(stdout, stderr):
    """`tmutil latestbackup` -> the text after "Last backup: ".

    tmutil exits 0 even when it cannot answer, and puts the reason on stderr —
    usually that the backup disk is not plugged in, which is not "no backups".
    """
    path = stdout.strip()
    if not path:
        if "mount" in stderr.lower():
            return "unknown — backup disk not connected"
        return "none found"
    name = Path(path).name
    stamp = name.removesuffix(".backup").removesuffix(".inprogress")
    try:
        return datetime.strptime(stamp, "%Y-%m-%d-%H%M%S").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return name


def tm_start_backup(parent):
    """Ask Time Machine to back up; say why not when it can't.

    `tmutil startbackup` exits 0 silently with no disk configured, so the
    destination has to be checked first or the request looks like it worked.
    """
    _, dest_xml, _ = run_cmd(["tmutil", "destinationinfo", "-X"], timeout=10)
    if not tm_has_destination(dest_xml):
        choice = QMessageBox.question(
            parent, "Time Machine",
            "Time Machine has no backup disk set up on this Mac.\n\n"
            "Open Time Machine settings to choose one?",
        )
        if choice == QMessageBox.StandardButton.Yes:
            run_cmd(["open", TM_SETTINGS_URL])
        return False
    rc, _, err = run_cmd(["tmutil", "startbackup"], timeout=10)
    if rc != 0:
        QMessageBox.warning(parent, "Time Machine",
                            f"Could not start backup:\n{err.strip() or f'tmutil exited {rc}'}")
        return False
    return True


class TimeMachineCard(Card):
    def __init__(self):
        super().__init__("Time Machine", "Backups to your Time Machine disk")

        self.last_lbl = QLabel("Checking…")
        self.body(self.last_lbl)

        self.status_lbl = QLabel("")
        self.body(self.status_lbl)

        row = QHBoxLayout()
        self.backup_btn = QPushButton("⏱ Back up now")
        self.backup_btn.clicked.connect(self._start_backup)
        refresh_btn = secondary_button("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh)
        row.addWidget(self.backup_btn)
        row.addWidget(refresh_btn)
        row.addStretch()
        self.body(row)

        self.refresh()

        self._timer = QTimer(self)
        self._timer.setInterval(5 * 60 * 1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def refresh(self):
        _, dest_xml, _ = run_cmd(["tmutil", "destinationinfo", "-X"], timeout=10)
        if not tm_has_destination(dest_xml):
            self.last_lbl.setText("Time Machine is not set up — no backup disk chosen.")
            self.status_lbl.setText("Status: off")
            self.backup_btn.setText("Set up Time Machine…")
            self.backup_btn.setEnabled(True)
            return
        self.backup_btn.setText("⏱ Back up now")

        _, out, err = run_cmd(["tmutil", "latestbackup"], timeout=10)
        self.last_lbl.setText(f"Last backup: {describe_tm_latest(out, err)}")

        _, status_xml, _ = run_cmd(["tmutil", "status", "-X"], timeout=10)
        running, phase, percent = parse_tm_status(status_xml)
        if running:
            detail = ", ".join(str(x) for x in (phase, f"{percent} %" if percent is not None else None) if x)
            self.status_lbl.setText(f"Status: backing up now…{f' ({detail})' if detail else ''}")
        else:
            self.status_lbl.setText("Status: idle")
        self.backup_btn.setEnabled(not running)

    def _start_backup(self):
        if tm_start_backup(self):
            self.status_lbl.setText("Status: backup requested…")
            self.backup_btn.setEnabled(False)
            QTimer.singleShot(5000, self.refresh)
        else:
            self.refresh()


# ----------------------------------------------------------------------------
# In-app documentation viewer
# ----------------------------------------------------------------------------
class DocViewerDialog(QDialog):
    def __init__(self, parent, title, path):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 720)
        layout = QVBoxLayout(self)

        viewer = QTextBrowser()
        viewer.setOpenExternalLinks(True)
        path = Path(path)
        if path.exists():
            viewer.setMarkdown(path.read_text(errors="replace"))
        else:
            viewer.setPlainText(f"File not found:\n{path}")
        layout.addWidget(viewer)

        row = QHBoxLayout()
        row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        layout.addLayout(row)


# ----------------------------------------------------------------------------
# Tools / quick links card
# ----------------------------------------------------------------------------
class ToolsCard(Card):
    def __init__(self):
        super().__init__("Tools & Links", "Open locations, docs, and provider account pages")
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(2)

        def col(title, items):
            box = QVBoxLayout()
            box.setSpacing(0)
            head = QLabel(title)
            head.setObjectName("TileName")
            box.addWidget(head)
            for text, target in items:
                b = link_button(text)
                if callable(target):
                    b.clicked.connect(target)
                else:
                    b.clicked.connect(lambda _, t=target: run_cmd(["open", str(t)]))
                box.addWidget(b)
            box.addStretch()
            return box

        app_dir = Path(__file__).resolve().parent
        locations = [
            ("Backup destination", DEST_ROOT),
            ("Backup logs", LOG_DIR),
            ("CloudStorage folder", CLOUD_DIR),
            ("iCloud Drive", ICLOUD_DIR),
            ("Time Machine settings", lambda: run_cmd(["open", TM_SETTINGS_URL])),
        ]
        docs = [
            ("App guide (README)", lambda _=False, t="App Guide", p=app_dir / "README.md": self.open_doc(t, p)),
            ("Backup strategy", lambda _=False, t="Backup Strategy", p=BACKUP_DIR / "BACKUP_STRATEGY.md": self.open_doc(t, p)),
            ("Google Drive setup", lambda _=False, t="Google Drive Setup", p=BACKUP_DIR / "SETUP.md": self.open_doc(t, p)),
            ("Proton vault guide", lambda _=False, t="Proton Vault Guide", p=BACKUP_DIR / "PROTON_VAULT.md": self.open_doc(t, p)),
            ("Lab overview", lambda _=False, t="Lab Overview", p=DOCS / "lab" / "README.md": self.open_doc(t, p)),
        ]
        accounts = [
            ("Google One storage", "https://one.google.com/storage"),
            ("Dropbox plan & usage", "https://www.dropbox.com/account/plan"),
            ("Proton storage dashboard", "https://account.proton.me/u/0/drive"),
            ("iCloud storage settings",
             lambda: run_cmd(["open", "x-apple.systempreferences:com.apple.systempreferences.AppleIDSettings"])),
        ]

        extras = [
            ("Google Photos Takeout…", self._google_photos_help),
            ("Proton vault status", self._proton_vault_check),
            ("Time Machine: back up now", lambda: tm_start_backup(self)),
        ]

        grid.addLayout(col("Open locations", locations), 0, 0)
        grid.addLayout(col("Documentation", docs), 0, 1)
        grid.addLayout(col("Account pages", accounts), 0, 2)
        grid.addLayout(col("Tools", extras), 1, 0)
        self.body(grid)

    def open_doc(self, title, path):
        DocViewerDialog(self, title, path).exec()

    def _google_photos_help(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Google Photos Takeout → Mac")
        msg.setText(
            "How to download your Google Photos library to this Mac:\n\n"
            "1.  Open takeout.google.com → Deselect all → tick Google Photos only.\n"
            "2.  Choose file type (.zip), frequency (once), and max size (2 GB).\n"
            "3.  Download the ZIP(s) when the email arrives.\n"
            "4.  Open the Photos app → File → Import → select the extracted folders.\n"
            "5.  After import, run Time Machine to include the Photos library in your\n"
            "    local backup.\n\n"
            "Tip: use 'google-photos-takeout-helper' (pip install) to merge multiple\n"
            "Takeout ZIPs into a single date-organised folder before importing."
        )
        msg.addButton("Open takeout.google.com", QMessageBox.ActionRole).clicked.connect(
            lambda: run_cmd(["open", "https://takeout.google.com"]))
        msg.addButton("Close", QMessageBox.RejectRole)
        msg.exec()

    def _proton_vault_check(self):
        vault_candidates = list(CLOUD_DIR.glob("ProtonDrive-*")) if CLOUD_DIR.exists() else []
        if not vault_candidates:
            QMessageBox.warning(self, "Proton Drive",
                                "No Proton Drive folder found in ~/Library/CloudStorage.\n"
                                "Is the Proton Drive desktop app running?")
            return
        issues = []
        for vault_path in vault_candidates:
            try:
                entries = list(vault_path.iterdir())
                if not entries:
                    issues.append(f"{vault_path.name}: folder is empty (not synced?).")
            except PermissionError:
                issues.append(f"{vault_path.name}: permission denied — check Full Disk Access.")
            except OSError as e:
                issues.append(f"{vault_path.name}: {e}")
        if issues:
            QMessageBox.warning(self, "Proton Drive", "\n".join(issues))
        else:
            names = ", ".join(p.name for p in vault_candidates)
            QMessageBox.information(self, "Proton Drive",
                                    f"Proton Drive appears accessible:\n{names}")


# ----------------------------------------------------------------------------
# Page scrolling with gesture latching
# ----------------------------------------------------------------------------
def fit_height_to_rows(view, min_rows=1):
    """Size a list or table to show every row, so it never scrolls inside the page.

    A box that scrolls inside a scrolling page is a trap for the wheel; one that
    is simply as tall as its contents is not. Only the backup log keeps a
    scrollbar of its own, because it is unbounded.
    """
    rows = view.model().rowCount()
    h = 2 * view.frameWidth()
    if isinstance(view, QTableWidget):
        if view.horizontalHeader().isVisibleTo(view):
            h += view.horizontalHeader().sizeHint().height()
        row_h = sum(view.rowHeight(r) for r in range(rows))
        h += row_h or view.verticalHeader().defaultSectionSize() * min_rows
    else:
        row_h = sum(view.sizeHintForRow(r) for r in range(rows))
        h += row_h or (view.fontMetrics().height() + 8) * min_rows
    if view.horizontalScrollBar().isVisible():
        h += view.horizontalScrollBar().sizeHint().height()
    view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    view.setFixedHeight(h)


class ResizableColumns(QObject):
    """Table columns you can drag to size, fitted automatically until you do.

    Until a border is dragged, `auto_fit` sizes the columns whenever the rows
    or the table's width change. After that the user's widths stand, and are
    kept in state.json so they survive a relaunch. Right-clicking the header
    offers "Fit columns to window" to hand control back. The last column always
    stretches to the table's edge.
    """
    STATE_KEY = "column_widths"

    def __init__(self, table, name, auto_fit):
        super().__init__(table)
        self.table, self.name, self._auto_fit = table, name, auto_fit
        self._fitting = False
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(40)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_menu)
        header.sectionResized.connect(self._section_resized)
        table.viewport().installEventFilter(self)

        saved = _load_state().get(self.STATE_KEY, {}).get(name)
        self.user_sized = isinstance(saved, list) and len(saved) == table.columnCount()
        if self.user_sized:
            self._fitting = True
            for col, width in enumerate(saved[:-1]):
                table.setColumnWidth(col, int(width))
            self._fitting = False

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save)

    def fit(self):
        if self.user_sized:
            return
        self._fitting = True
        try:
            self._auto_fit()
            # The stretched last column never shrinks below the width it had
            # before stretching (100 px at creation), which pushed a narrow
            # Size column past the table's edge. Floor it so the stretch decides.
            header = self.table.horizontalHeader()
            header.resizeSection(self.table.columnCount() - 1, header.minimumSectionSize())
        finally:
            self._fitting = False

    def reset(self):
        self.user_sized = False
        state = _load_state()
        state.get(self.STATE_KEY, {}).pop(self.name, None)
        _save_state(state)
        self.fit()

    def save(self):
        state = _load_state()
        state.setdefault(self.STATE_KEY, {})[self.name] = [
            self.table.columnWidth(c) for c in range(self.table.columnCount())]
        _save_state(state)

    def _section_resized(self, *_):
        # Every width change we make is inside fit(); a stretch of the last
        # section is the table resizing, not the user. Anything else is a drag.
        if self._fitting or self.table.horizontalHeader().sectionResizeMode(0) != QHeaderView.Interactive:
            return
        if not (QApplication.mouseButtons() & Qt.LeftButton):
            return
        self.user_sized = True
        self._save_timer.start()

    def _header_menu(self, pos):
        menu = QMenu(self.table)
        fit_action = menu.addAction("Fit columns to window")
        fit_action.setEnabled(self.user_sized)
        if menu.exec(self.table.horizontalHeader().mapToGlobal(pos)) == fit_action:
            self.reset()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            self.fit()
        return False


class SmartScrollArea(QScrollArea):
    """Routes each scroll gesture to one place for its whole length.

    This is how Safari and native Mac views behave: an inner box (the backup
    log) takes the wheel only when the gesture *starts* over it and it can
    still move that way; otherwise the page scrolls, and keeps scrolling when
    the pointer then drifts over a box. The previous version sent every event
    to whatever box was under the pointer, so a page scroll stalled the moment
    one passed beneath the cursor.

    A gesture is a trackpad ScrollBegin…momentum…ScrollEnd sequence, or, for a
    mouse wheel (no phases), a run of clicks less than GESTURE_GAP_MS apart.
    """
    GESTURE_GAP_MS = 300

    def __init__(self, parent=None):
        super().__init__(parent)
        self._latched = None    # scrollbar that owns the current gesture
        self._origin = None     # widget the current gesture started over
        self._last_ms = None
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Wheel and isinstance(obj, QWidget)
                and self.isAncestorOf(obj)):
            self._route(obj, event)
            return True
        return False

    def _is_new_gesture(self, event, now):
        phase = event.phase()
        if phase == Qt.ScrollBegin:
            return True
        if phase == Qt.NoScrollPhase:
            return self._last_ms is None or now - self._last_ms > self.GESTURE_GAP_MS
        return self._latched is None and self._origin is None

    @staticmethod
    def _bar_for(area, event):
        d = event.angleDelta()
        return area.horizontalScrollBar() if abs(d.x()) > abs(d.y()) else area.verticalScrollBar()

    @staticmethod
    def _deliver(bar, event):
        # Straight to the bar's handler: no event filters, no propagation to
        # parents, and isAccepted() then says whether the bar actually moved.
        event.ignore()
        bar.event(event)
        return event.isAccepted()

    def _route(self, obj, event):
        now = int(datetime.now().timestamp() * 1000)
        if self._is_new_gesture(event, now):
            self._latched, self._origin = None, obj
        self._last_ms = now

        if self._latched is None:
            if event.angleDelta().isNull() and event.pixelDelta().isNull():
                return  # ScrollBegin carries no movement; decide on the first that does
            w = self._origin if self._origin is not None else obj
            while w is not None and w is not self:
                if isinstance(w, QAbstractScrollArea):
                    bar = self._bar_for(w, event)
                    if bar.maximum() > bar.minimum() and self._deliver(bar, event):
                        self._latched = bar
                        return
                w = w.parentWidget()
            self._latched = self._bar_for(self, event)

        try:
            self._deliver(self._latched, event)
        except RuntimeError:  # the latched box was deleted mid-gesture
            self._latched = self._bar_for(self, event)
            self._deliver(self._latched, event)


# ----------------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # The build is part of the app's identity, not a detail hidden in an
        # About box: "is this the one I just built" is asked far more often
        # than it is answered.
        self.setWindowTitle(f"Backup Control Center {version.version_string()}")
        self.resize(1120, 860)
        self.setMinimumWidth(1020)

        scroll = SmartScrollArea()
        scroll.setObjectName("ScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setObjectName("ScrollContent")
        outer = QVBoxLayout(content)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Backup Control Center")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Dashboard, Google Drive backup, and storage at a glance")
        subtitle.setObjectName("AppSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        refresh_btn = secondary_button("🔄 Refresh all")
        refresh_btn.clicked.connect(self.refresh_all)
        header.addWidget(refresh_btn)
        self._theme_btn = secondary_button("☀" if _DARK else "🌙")
        self._theme_btn.setFixedWidth(36)
        self._theme_btn.clicked.connect(self._toggle_theme)
        header.addWidget(self._theme_btn)
        settings_btn = secondary_button("⚙")
        settings_btn.setFixedWidth(36)
        settings_btn.clicked.connect(self._open_settings)
        header.addWidget(settings_btn)
        outer.addLayout(header)

        self.storage_card = StorageCard()
        self.backup_card = BackupStatusCard()
        self.folders_card = FoldersCard()
        self.health_card = LabHealthCard()
        self.tm_card = TimeMachineCard()
        self.tools_card = ToolsCard()

        outer.addWidget(self.storage_card)
        outer.addWidget(self.backup_card)
        outer.addWidget(self.folders_card)
        outer.addWidget(self.health_card)
        outer.addWidget(self.tm_card)
        outer.addWidget(self.tools_card)
        outer.addStretch()

        scroll.setWidget(content)
        self.setCentralWidget(scroll)

        # Single-folder quick backup from Folders card right-click.
        self.folders_card.single_backup_requested.connect(self.backup_card.run_single_folder)

        # Tray icon — patch backup_card._finished to keep tray in sync.
        self.tray = BackupTrayIcon(self)
        original_finished = self.backup_card._finished

        def _patched_finished():
            original_finished()
            self.tray.update_status()

        self.backup_card._finished = _patched_finished

        # Watch for a second launch asking us to un-hide. The directory is
        # watched rather than the file, because a watch on a file that gets
        # created and deleted repeatedly does not survive the delete.
        try:
            cloud_quota.SECRETS_DIR.mkdir(parents=True, exist_ok=True)
            _SHOW_REQUEST_FILE.unlink(missing_ok=True)  # ignore a stale request
            self._show_watcher = QFileSystemWatcher([str(cloud_quota.SECRETS_DIR)], self)
            self._show_watcher.directoryChanged.connect(self._on_show_requested)
        except OSError:
            self._show_watcher = None

        # Live dark mode: re-theme when system appearance changes.
        QApplication.instance().paletteChanged.connect(self._on_palette_changed)

    def _on_show_requested(self, _path):
        """A second launch asked us to come back. Fires on any write in the
        settings dir (state.json included), so the request file gates it."""
        if not _SHOW_REQUEST_FILE.exists():
            return
        try:
            _SHOW_REQUEST_FILE.unlink()
        except OSError:
            pass
        # Reuses the tray's Open, which restores the dock tile before raising —
        # an accessory app cannot take focus, so the order matters.
        self.tray._show_window()

    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self.backup_card.refresh_schedule()
            self.backup_card.refresh_wake()

    def _toggle_theme(self):
        global _DARK
        _DARK = not _DARK
        QApplication.instance().setStyleSheet(build_app_style(_DARK))
        self._theme_btn.setText("☀" if _DARK else "🌙")
        self.storage_card.refresh()

    def _on_palette_changed(self, _palette=None):
        new_dark = _system_dark_mode()
        global _DARK
        if new_dark != _DARK:
            _DARK = new_dark
            QApplication.instance().setStyleSheet(build_app_style(_DARK))
            self._theme_btn.setText("☀" if _DARK else "🌙")
            self.storage_card.refresh()

    def closeEvent(self, event):
        self.backup_card.save_log_scroll()
        event.ignore()
        if self.isFullScreen():
            # Hiding a window that owns a macOS fullscreen Space leaves the Space
            # behind with nothing drawn in it — a black screen the user has to
            # escape by hand. Leave fullscreen first and hide once the (animated)
            # transition has finished; hiding mid-animation strands it just the
            # same.
            self.showNormal()
            QTimer.singleShot(750, self._hide_to_tray)
        else:
            self._hide_to_tray()

    def _hide_to_tray(self):
        self.hide()
        # Drop the dock tile here rather than at the call sites, so it happens
        # after any fullscreen exit has completed and every hide path matches.
        _set_dock_icon_visible(False)
        if _load_state().get("hide_on_close", False):
            self.tray.showMessage(
                "Backup Control Center",
                "Running in the menu bar. Click the icon to restore.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    def refresh_all(self):
        self.storage_card.refresh()
        self.backup_card.refresh_status()
        self.backup_card.refresh_schedule()
        self.folders_card.reload_folders()
        self.health_card.rescan()
        self.tm_card.refresh()
        self.tray.update_status()


# ----------------------------------------------------------------------------
# Menu-bar / system-tray companion
# ----------------------------------------------------------------------------
class BackupTrayIcon(QSystemTrayIcon):
    def __init__(self, window):
        super().__init__()
        self._window = window

        # Use the app's icon asset if available, fall back to a built-in stock icon.
        icon_path = Path(__file__).resolve().parent / "assets" / "icon.icns"
        if icon_path.exists():
            self._normal_icon = QIcon(str(icon_path))
        else:
            self._normal_icon = QIcon.fromTheme("document-save",
                               QApplication.style().standardIcon(
                                   QApplication.style().StandardPixmap.SP_DriveHDIcon))
        self._warning_icon = self._make_warning_icon(self._normal_icon)
        self.setIcon(self._normal_icon)

        menu = QMenu()
        self._status_action = menu.addAction("Checking…")
        self._status_action.setEnabled(False)
        menu.addSeparator()
        show_action = menu.addAction("Open")
        show_action.triggered.connect(self._show_window)
        menu.addSeparator()
        dry_action = menu.addAction("Dry run")
        dry_action.triggered.connect(lambda: (self._show_window(),
                                              window.backup_card.run_dry_run()))
        run_action = menu.addAction("Sync now")
        run_action.triggered.connect(lambda: (self._show_window(),
                                              window.backup_card.run_backup()))
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit)
        self.setContextMenu(menu)

        # No activated handler: clicking the icon should only open the menu.
        # "Open" in that menu is the one way to raise the window.
        self.update_status()
        self.show()

    @staticmethod
    def _make_warning_icon(base: QIcon) -> QIcon:
        from PySide6.QtGui import QPainter, QBrush
        px = base.pixmap(64, 64)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#FF9500")))
        p.drawEllipse(42, 42, 20, 20)
        p.end()
        return QIcon(px)

    def update_status(self, info: str | None = None):
        if info is None:
            info, _ = last_backup_info()
        short = info.replace("Last run: ", "").replace("No backups run yet.", "Never backed up")
        age = last_backup_age_hours()
        if age is not None and age > 25:
            self.setIcon(self._warning_icon)
            short = f"⚠ {short}"
        else:
            self.setIcon(self._normal_icon)
        self.setToolTip(f"Backup Control Center\n{short}")
        self._status_action.setText(short)

    def _quit(self):
        # The one real exit. No confirmation dialog: with the window hidden a
        # parentless modal never comes to front, which made this path look dead.
        global _REALLY_QUITTING
        _REALLY_QUITTING = True
        try:
            self._window.backup_card.save_log_scroll()
        except Exception:
            pass
        # Hard exit rather than QApplication.quit(). This is the only path out
        # of the app, and half a dozen QThreads (iCloud `du -sk`, folder sizing,
        # Lab Health scan) may be mid-run; an exit that can be delayed by any of
        # them is not worth the risk here. State is saved, nothing to unwind.
        os._exit(0)

    def _show_window(self):
        # Back into the dock first: a Regular app can take focus, an Accessory
        # one cannot, so raise/activate below would otherwise do nothing.
        _set_dock_icon_visible(True)
        if self._window.isMinimized():
            self._window.setWindowState(
                self._window.windowState() & ~Qt.WindowMinimized)
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()


# ----------------------------------------------------------------------------
# Settings dialog
# ----------------------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        state = _load_state()

        self._hide_chk = QCheckBox("Hide to menu bar on close (don't quit)")
        self._hide_chk.setChecked(state.get("hide_on_close", False))
        layout.addWidget(self._hide_chk)

        note = QLabel(
            "When enabled, closing the window keeps the app running in the menu bar. "
            "Use Quit from the menu-bar icon to fully exit."
        )
        note.setWordWrap(True)
        note.setObjectName("CardSubtitle")
        layout.addWidget(note)

        layout.addWidget(QLabel("Nightly backup time:"))
        time_row = QHBoxLayout()
        self._hour_spin = QSpinBox()
        self._hour_spin.setRange(0, 23)
        self._hour_spin.setValue(state.get("backup_hour", 3))
        self._hour_spin.setSuffix("h")
        self._minute_spin = QSpinBox()
        self._minute_spin.setRange(0, 59)
        self._minute_spin.setSingleStep(15)
        self._minute_spin.setValue(state.get("backup_minute", 30))
        self._minute_spin.setSuffix("m")
        time_row.addWidget(self._hour_spin)
        time_row.addWidget(self._minute_spin)
        time_row.addStretch()
        layout.addLayout(time_row)

        time_note = QLabel("The app must be open and 🕒 Nightly schedule must be enabled.")
        time_note.setWordWrap(True)
        time_note.setObjectName("CardSubtitle")
        layout.addWidget(time_note)

        self._mirror_chk = QCheckBox("Mirror mode — delete from Drive what you delete locally")
        self._mirror_chk.setChecked(state.get("mirror_mode", False))
        layout.addWidget(self._mirror_chk)

        mirror_note = QLabel(
            "Off by default, so the backup only ever grows and old files linger. "
            "On, each run removes backed-up files that no longer exist on this Mac — "
            "they are moved to Backups/MacBook/_deleted/&lt;date&gt;/ rather than destroyed, "
            "so mistakes stay recoverable. Run <b>Preview deletions</b> first."
        )
        mirror_note.setWordWrap(True)
        mirror_note.setObjectName("CardSubtitle")
        layout.addWidget(mirror_note)

        layout.addWidget(QLabel("Webhook URL on failure (optional):"))
        self._webhook_edit = QLineEdit()
        self._webhook_edit.setPlaceholderText("https://ntfy.sh/your-topic  or  https://hooks.slack.com/…")
        self._webhook_edit.setText(state.get("webhook_url", ""))
        layout.addWidget(self._webhook_edit)

        webhook_note = QLabel(
            "A POST is sent here when a backup finishes with errors. "
            "Works with ntfy, Slack, Pushover, or any webhook endpoint."
        )
        webhook_note.setWordWrap(True)
        webhook_note.setObjectName("CardSubtitle")
        layout.addWidget(webhook_note)

        layout.addStretch()

        row = QHBoxLayout()
        row.addStretch()
        cancel_btn = secondary_button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        row.addWidget(cancel_btn)
        row.addWidget(save_btn)
        layout.addLayout(row)

    def _save(self):
        state = _load_state()
        # Turning mirroring on makes every later run destructive, so confirm it
        # here rather than letting it ride along with the other settings.
        turning_on = self._mirror_chk.isChecked() and not state.get("mirror_mode", False)
        if turning_on:
            answer = QMessageBox.warning(
                self, "Enable mirror mode?",
                "From the next backup on, deleting a file on this Mac will also "
                "remove it from Google Drive.\n\n"
                "Deleted copies are kept in Backups/MacBook/_deleted/<date>/, so "
                "this is recoverable — but only for as long as you keep those "
                "folders.\n\n"
                "Have you run Preview deletions and checked the list?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                self._mirror_chk.setChecked(False)
                return
        state["hide_on_close"] = self._hide_chk.isChecked()
        state["backup_hour"] = self._hour_spin.value()
        state["backup_minute"] = self._minute_spin.value()
        state["webhook_url"] = self._webhook_edit.text().strip()
        state["mirror_mode"] = self._mirror_chk.isChecked()
        _save_state(state)
        self.accept()


_INSTANCE_LOCK_FILE = cloud_quota.SECRETS_DIR / "gui.lock"
_instance_lock_fd = None  # kept open so the OS holds the lock for our lifetime

# How a second launch reaches the running copy — one of two ways, because macOS
# does not behave consistently here:
#
#   * While the app is ACCESSORY (after a Quit), LaunchServices does start a
#     second process. It hits the lock, drops this file, and exits; the running
#     copy is watching for it and un-hides.
#   * While the app is a normal FOREGROUND app with a hidden window (what
#     --background produces), LaunchServices starts nothing at all. It sends a
#     reopen Apple Event to the running instance instead, so no second process
#     exists to write anything — that arrives as QEvent.ApplicationActivate and
#     is handled in QuitInterceptApp.
#
# Missing the second case is why launching from Lab Hub took focus, showed the
# app in the menu bar, and never put a window on screen.
_SHOW_REQUEST_FILE = cloud_quota.SECRETS_DIR / "show_request"


def _acquire_instance_lock():
    """Grab an exclusive flock on a lock file. Returns True for the first instance."""
    global _instance_lock_fd
    cloud_quota.SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd = open(_INSTANCE_LOCK_FILE, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(str(os.getpid()))
        fd.flush()
        _instance_lock_fd = fd  # keep fd alive so the lock holds
        return True
    except BlockingIOError:
        return False


class QuitInterceptApp(QApplication):
    """QApplication that stays alive in the menu bar when the user quits.

    macOS routes both Cmd+Q and the dock's right-click -> Quit to QEvent.Quit,
    which Qt honours even with setQuitOnLastWindowClosed(False). Swallowing it
    keeps the tray icon — and with it the nightly schedule, network trigger and
    USB trigger — running. The tray's own Quit sets _REALLY_QUITTING first, so
    that one path exits for real.
    """

    def __init__(self, argv):
        super().__init__(argv)
        self._main_window = None
        # Activation events fire while the app is still coming up. Honouring
        # those would pop a window open in --background mode, which exists
        # precisely to start without one, so ignore anything in the first
        # couple of seconds.
        self._accepts_reopen = False
        QTimer.singleShot(2500, lambda: setattr(self, "_accepts_reopen", True))

    def set_window(self, win):
        self._main_window = win

    def event(self, e):
        # Reopen: launching an already-running foreground app starts no second
        # process, so nothing can signal us through the show-request file — this
        # event is the only notice we get. Only act when there is no window up,
        # so ordinary re-focus (⌘-Tab, clicking the dock tile of a visible app)
        # is left alone.
        if (e.type() == QEvent.ApplicationActivate
                and self._accepts_reopen
                and self._main_window is not None
                and not self._main_window.isVisible()):
            self._main_window.tray._show_window()
            return True
        if e.type() == QEvent.Quit and not _REALLY_QUITTING:
            e.ignore()
            if self._main_window is not None:
                # closeEvent ignores it, leaves fullscreen if needed, then hides
                # and drops the dock tile once the transition is done.
                self._main_window.close()
                # Say where the app went and how to leave for real — otherwise a
                # refused Quit is indistinguishable from the app being stuck.
                self._main_window.tray.showMessage(
                    "Still running in the menu bar",
                    "Backups keep running. To exit fully: menu bar icon → Quit.",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
            return True
        return super().event(e)


def main():
    background = "--background" in sys.argv
    if background:
        sys.argv.remove("--background")
    if not _acquire_instance_lock():
        if background:
            sys.exit(0)
        # Ask the running copy to show itself, then get out of the way. No alert:
        # launching the app should just bring it up, and the old alert fired even
        # when the running copy was invisible, which read as "it won't open".
        try:
            cloud_quota.SECRETS_DIR.mkdir(parents=True, exist_ok=True)
            _SHOW_REQUEST_FILE.write_text(datetime.now().isoformat())
        except OSError:
            # Signalling failed, so say something rather than exiting silently.
            subprocess.run(
                ["osascript", "-e",
                 'display alert "Backup Control Center is already running." '
                 'message "Use its menu bar icon to open the window." '
                 'buttons {"OK"} default button "OK" giving up after 8'],
                check=False,
            )
        sys.exit(0)

    global _DARK
    _DARK = _system_dark_mode()
    app = QuitInterceptApp(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    if background:
        # Before the window exists, so the dock tile is never claimed. The app
        # is Regular by default (no LSUIElement in the bundle), and a login
        # launch that takes the dock and the foreground is the thing --background
        # is for.
        _set_dock_icon_visible(False)
    app.setStyleSheet(build_app_style(_DARK))
    win = MainWindow()
    app.set_window(win)
    if not background:
        win.show()
    # Runs after the window exists so a failure here cannot stop the app coming up.
    migrate_login_item()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
