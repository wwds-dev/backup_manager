"""
Real cloud-account storage quota (used/total) for Google Drive and Dropbox,
via each provider's OAuth API — distinct from local filesystem free space.

Proton Drive and iCloud have no public API, so they aren't covered here; their
tiles in the app fall back to local disk free space.

One-time setup required from the user (can't be done on their behalf):
  Google  - console.cloud.google.com -> new project -> enable "Google Drive API"
            -> OAuth consent screen (External, add yourself as test user)
            -> Credentials -> Create OAuth client ID -> Application type "Desktop app"
            -> note the Client ID and Client Secret
            -> under that client's settings, no redirect URI registration needed
               (Desktop app type allows any loopback port)
  Dropbox - dropbox.com/developers/apps -> Create app -> Scoped access ->
            "App folder" or "Full Dropbox" access type (doesn't matter for quota)
            -> Permissions tab -> enable "account_info.read" -> Submit
            -> Settings tab -> note the App key and App secret
            -> Settings tab -> Redirect URIs -> add http://localhost:53789/

Then, in the app's Cloud Accounts dialog, paste those values in and click
Connect for each Google Drive / Dropbox mount — a browser window opens for you
to sign in and approve access for that specific account.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import requests

SECRETS_DIR = Path.home() / "Library" / "Application Support" / "Backup Control Center"
CREDENTIALS_FILE = SECRETS_DIR / "app_credentials.json"
TOKENS_FILE = SECRETS_DIR / "tokens.json"
MANUAL_ACCOUNTS_FILE = SECRETS_DIR / "manual_accounts.json"

REDIRECT_PORT = 53789
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/drive.metadata.readonly"

DROPBOX_AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
DROPBOX_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
DROPBOX_SCOPE = "account_info.read"


# ----------------------------------------------------------------------------
# Quota result. A (used, total) pair that existing callers unpack unchanged,
# carrying an optional Google Drive split as attributes.
# ----------------------------------------------------------------------------
class Quota(tuple):
    """(used, total) with optional `.drive` (usageInDrive) and `.trash` (usageInDriveTrash)."""

    def __new__(cls, used, total, drive=None, trash=None):
        self = super().__new__(cls, (used, total))
        self.drive = drive
        self.trash = trash
        return self


def drive_split(used, drive, trash):
    """(drive_files, other, trash) for the Google tile.

    `other` is `used - drive`, a difference and not a read value (Photos and Gmail cannot be
    told apart). It is given only when `drive` is known and 0 <= drive <= used; otherwise the
    first two are None. Trash is passed through and never subtracted.
    """
    if drive is None or drive < 0 or drive > used:
        return None, None, trash
    return drive, used - drive, trash


# ----------------------------------------------------------------------------
# Local storage for the OAuth client app credentials and per-account tokens.
# Never commit .secrets/ — it's gitignored.
# ----------------------------------------------------------------------------
def _read_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (ValueError, OSError):
            return {}
    return {}


def _write_json(path, data):
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    os.chmod(path, 0o600)


def load_app_credentials():
    return _read_json(CREDENTIALS_FILE)


def save_app_credentials(data):
    _write_json(CREDENTIALS_FILE, data)


def load_tokens():
    return _read_json(TOKENS_FILE)


def save_tokens(data):
    _write_json(TOKENS_FILE, data)


def is_connected(account_key):
    return account_key in load_tokens()


def load_manual_accounts():
    """List of {"key", "provider", "label"} for accounts added via + Add account
    that aren't backed by a local CloudStorage mount."""
    data = _read_json(MANUAL_ACCOUNTS_FILE)
    return data.get("accounts", [])


def save_manual_accounts(accounts):
    _write_json(MANUAL_ACCOUNTS_FILE, {"accounts": accounts})


def add_manual_account(key, provider, label):
    accounts = load_manual_accounts()
    if not any(a["key"] == key for a in accounts):
        accounts.append({"key": key, "provider": provider, "label": label})
        save_manual_accounts(accounts)


def remove_manual_account(key):
    accounts = [a for a in load_manual_accounts() if a["key"] != key]
    save_manual_accounts(accounts)
    disconnect(key)


def disconnect(account_key):
    tokens = load_tokens()
    tokens.pop(account_key, None)
    save_tokens(tokens)


# ----------------------------------------------------------------------------
# One-shot local HTTP server to catch the OAuth redirect.
#
# Only one of these can be listening on REDIRECT_PORT at a time. If a previous
# attempt was abandoned (browser closed, consent blocked, user clicked Connect
# again before it timed out) its server is still bound to the port — so before
# starting a new one we explicitly close out whatever's currently tracked here.
# ----------------------------------------------------------------------------
class _ReusableHTTPServer(http.server.HTTPServer):
    allow_reuse_address = True


_active_server_lock = threading.Lock()
_active_server = None


def _close_active_server():
    global _active_server
    with _active_server_lock:
        if _active_server is not None:
            try:
                _active_server.shutdown()
                _active_server.server_close()
            except OSError:
                pass
            _active_server = None


def _wait_for_redirect(port, timeout=180):
    global _active_server
    _close_active_server()

    result = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.urlparse(self.path).query
            result.update(urllib.parse.parse_qs(qs))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body>Connected. You can close this tab and "
                b"return to Backup Control Center.</body></html>"
            )
            done.set()

        def log_message(self, *args):
            pass

    server = _ReusableHTTPServer(("127.0.0.1", port), Handler)
    with _active_server_lock:
        _active_server = server
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    done.wait(timeout)
    _close_active_server()
    return result


# ----------------------------------------------------------------------------
# Google Drive
# ----------------------------------------------------------------------------
def google_connect(account_key):
    creds = load_app_credentials().get("google")
    if not creds or not creds.get("client_id"):
        return False, "No Google Client ID / Secret saved yet."

    params = {
        "client_id": creds["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    webbrowser.open(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")
    result = _wait_for_redirect(REDIRECT_PORT)
    code = result.get("code", [None])[0]
    if not code:
        return False, "No authorization code received (timed out or denied)."

    resp = requests.post(GOOGLE_TOKEN_URL, data={
        "code": code,
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=20)
    if resp.status_code != 200:
        return False, f"Token exchange failed: {resp.text[:200]}"
    data = resp.json()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return False, "Google did not return a refresh token (try disconnecting app access in your Google Account and reconnecting)."

    tokens = load_tokens()
    tokens[account_key] = {"provider": "google", "refresh_token": refresh_token}
    save_tokens(tokens)
    return True, None


def _google_access_token(refresh_token):
    creds = load_app_credentials().get("google")
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }, timeout=20)
    resp.raise_for_status()
    return resp.json()["access_token"]


def google_quota(account_key):
    """Returns (used_bytes, total_bytes_or_None) or raises on error."""
    entry = load_tokens().get(account_key)
    if not entry:
        return None
    access_token = _google_access_token(entry["refresh_token"])
    resp = requests.get(
        "https://www.googleapis.com/drive/v3/about",
        params={"fields": "storageQuota"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    resp.raise_for_status()
    quota = resp.json().get("storageQuota", {})
    used = int(quota.get("usage", 0))
    total = int(quota["limit"]) if "limit" in quota else None  # unlimited plans omit it
    drive = int(quota["usageInDrive"]) if "usageInDrive" in quota else None
    trash = int(quota["usageInDriveTrash"]) if "usageInDriveTrash" in quota else None
    return Quota(used, total, drive=drive, trash=trash)


# ----------------------------------------------------------------------------
# Dropbox
# ----------------------------------------------------------------------------
def _pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def dropbox_connect(account_key):
    creds = load_app_credentials().get("dropbox")
    if not creds or not creds.get("app_key"):
        return False, "No Dropbox App Key / Secret saved yet."

    verifier, challenge = _pkce_pair()
    params = {
        "client_id": creds["app_key"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "token_access_type": "offline",
        "scope": DROPBOX_SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    webbrowser.open(f"{DROPBOX_AUTH_URL}?{urllib.parse.urlencode(params)}")
    result = _wait_for_redirect(REDIRECT_PORT)
    code = result.get("code", [None])[0]
    if not code:
        return False, "No authorization code received (timed out or denied)."

    resp = requests.post(DROPBOX_TOKEN_URL, data={
        "code": code,
        "grant_type": "authorization_code",
        "client_id": creds["app_key"],
        "client_secret": creds["app_secret"],
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }, timeout=20)
    if resp.status_code != 200:
        return False, f"Token exchange failed: {resp.text[:200]}"
    data = resp.json()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return False, "Dropbox did not return a refresh token."

    tokens = load_tokens()
    tokens[account_key] = {"provider": "dropbox", "refresh_token": refresh_token}
    save_tokens(tokens)
    return True, None


def _dropbox_access_token(refresh_token):
    creds = load_app_credentials().get("dropbox")
    resp = requests.post(DROPBOX_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": creds["app_key"],
        "client_secret": creds["app_secret"],
    }, timeout=20)
    resp.raise_for_status()
    return resp.json()["access_token"]


def dropbox_account_email(account_key):
    """Returns the email address for a connected Dropbox account, or None."""
    entry = load_tokens().get(account_key)
    if not entry or entry["provider"] != "dropbox":
        return None
    try:
        access_token = _dropbox_access_token(entry["refresh_token"])
        resp = requests.post(
            "https://api.dropboxapi.com/2/users/get_current_account",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("email")
    except Exception:
        return None


def dropbox_quota(account_key):
    """Returns (used_bytes, total_bytes_or_None) or raises on error."""
    entry = load_tokens().get(account_key)
    if not entry:
        return None
    access_token = _dropbox_access_token(entry["refresh_token"])
    resp = requests.post(
        "https://api.dropboxapi.com/2/users/get_space_usage",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    used = int(data.get("used", 0))
    allocation = data.get("allocation", {})
    total = allocation.get("allocated")
    if total is None:
        # team allocations nest it differently
        total = allocation.get("team", {}).get("allocated")
    return used, (int(total) if total is not None else None)


# ----------------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------------
def provider_for_name(name):
    lower = name.lower()
    if lower.startswith("googledrive"):
        return "google"
    if lower.startswith("dropbox"):
        return "dropbox"
    return None


def connect(provider, account_key):
    if provider == "google":
        return google_connect(account_key)
    if provider == "dropbox":
        return dropbox_connect(account_key)
    return False, f"Unknown provider: {provider}"


def quota(account_key):
    entry = load_tokens().get(account_key)
    if not entry:
        return None
    if entry["provider"] == "google":
        return google_quota(account_key)
    if entry["provider"] == "dropbox":
        return dropbox_quota(account_key)
    return None
