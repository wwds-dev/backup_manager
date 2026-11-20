"""
Real cloud-account storage quota (used/total) for Google Drive, Dropbox and
OneDrive, via each provider's OAuth API — distinct from local filesystem free space.

Proton Drive and iCloud have no public quota API, so they have no quota call here
(registry entries with has_quota=False): Proton shows a link-only tile, iCloud its
local `du` figure.

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
Connect for each Google Drive / Dropbox / OneDrive mount — a browser window opens for you
to sign in and approve access for that specific account.
"""

import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import tempfile
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
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


def _ensure_secrets_dir():
    """Create the secrets folder owner-only (0700), and tighten one an older build left 0755."""
    SECRETS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(SECRETS_DIR, 0o700)


def load_app_credentials():
    return _read_json(CREDENTIALS_FILE)


def save_app_credentials(data):
    _write_json_atomic(CREDENTIALS_FILE, data)


def _write_json_atomic(path, data):
    """Write `data` to `path` as 0600 via a temp file in the same folder and os.replace,
    so a reader never sees a half-written file and a failed write leaves the old one.
    Every secrets file (credentials, tokens, manual accounts) is written this way."""
    _ensure_secrets_dir()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(data, indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# Every read-modify-write of tokens.json holds this lock, so two writers (a refresh
# storing a rotated token, a connect, a disconnect) cannot lose each other's change.
_TOKENS_LOCK = threading.RLock()


def load_tokens():
    return _read_json(TOKENS_FILE)


def save_tokens(data):
    with _TOKENS_LOCK:
        _write_json_atomic(TOKENS_FILE, data)


def _set_token_entry(account_key, entry):
    with _TOKENS_LOCK:
        tokens = load_tokens()
        tokens[account_key] = entry
        save_tokens(tokens)


def _store_refresh_token(account_key, new_token):
    """Store a rotated refresh token for an existing account, keeping its other fields.
    An account removed meanwhile stays removed: nothing is written for it."""
    with _TOKENS_LOCK:
        tokens = load_tokens()
        if account_key not in tokens:
            return
        entry = dict(tokens[account_key])
        entry["refresh_token"] = new_token
        tokens[account_key] = entry
        save_tokens(tokens)


_refresh_locks = {}
_refresh_locks_guard = threading.Lock()


def _refresh_lock(account_key):
    """One lock per account around refresh-then-store: with single-use refresh tokens two
    overlapping refreshes would otherwise send the same token and one would be rejected."""
    with _refresh_locks_guard:
        return _refresh_locks.setdefault(account_key, threading.Lock())


def is_connected(account_key):
    return account_key in load_tokens()


def load_manual_accounts():
    """List of {"key", "provider", "label"} for accounts added via + Add account
    that aren't backed by a local CloudStorage mount."""
    data = _read_json(MANUAL_ACCOUNTS_FILE)
    return data.get("accounts", [])


def save_manual_accounts(accounts):
    _write_json_atomic(MANUAL_ACCOUNTS_FILE, {"accounts": accounts})


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
    # The account's refresh lock first (same order as a refresh: refresh lock, then
    # tokens lock), so a refresh in flight finishes before the entry is removed.
    with _refresh_lock(account_key), _TOKENS_LOCK:
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
class _ReusableHTTPServer(http.server.ThreadingHTTPServer):
    """One thread per request, so a connection that never sends a request cannot hold up the
    real redirect or `shutdown()`. Request threads are daemons and never joined on close."""
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False


# Seconds a redirect connection may sit idle before its handler gives up (socket timeout).
_REDIRECT_REQUEST_TIMEOUT = 5


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
    claim = threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        timeout = _REDIRECT_REQUEST_TIMEOUT

        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            # Only a sign-in response ends the wait; a stray request (favicon, a probe)
            # is answered 404 and the listener keeps waiting. The first response wins.
            if "code" not in query and "error" not in query:
                self.send_error(404)
                return
            with claim:
                first = not done.is_set()
                if first:
                    result.update(query)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body>Connected. You can close this tab and "
                b"return to Backup Control Center.</body></html>"
            )
            if first:
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

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": creds["client_id"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    webbrowser.open(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")
    code, error = _redirect_code(_wait_for_redirect(REDIRECT_PORT), state)
    if error:
        return False, error

    resp = requests.post(GOOGLE_TOKEN_URL, data={
        "code": code,
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }, timeout=20)
    if resp.status_code != 200:
        return False, f"Token exchange failed: {_oauth_error_text(resp)}"
    data = resp.json()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return False, "Google did not return a refresh token (try disconnecting app access in your Google Account and reconnecting)."

    _set_token_entry(account_key, {"provider": "google", "refresh_token": refresh_token})
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
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": creds["app_key"],
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "token_access_type": "offline",
        "scope": DROPBOX_SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    webbrowser.open(f"{DROPBOX_AUTH_URL}?{urllib.parse.urlencode(params)}")
    code, error = _redirect_code(_wait_for_redirect(REDIRECT_PORT), state)
    if error:
        return False, error

    resp = requests.post(DROPBOX_TOKEN_URL, data={
        "code": code,
        "grant_type": "authorization_code",
        "client_id": creds["app_key"],
        "client_secret": creds["app_secret"],
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }, timeout=20)
    if resp.status_code != 200:
        return False, f"Token exchange failed: {_oauth_error_text(resp)}"
    data = resp.json()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return False, "Dropbox did not return a refresh token."

    _set_token_entry(account_key, {"provider": "dropbox", "refresh_token": refresh_token})
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
# OneDrive (Microsoft Graph). Public client: PKCE, no secret; only the client ID
# is stored. Entra matches any port on a registered http://localhost redirect.
# Microsoft returns a new refresh token on refresh; it is stored each time.
# ----------------------------------------------------------------------------
ONEDRIVE_AUTHORITY = "https://login.microsoftonline.com/common/oauth2/v2.0"
ONEDRIVE_AUTH_URL = f"{ONEDRIVE_AUTHORITY}/authorize"
ONEDRIVE_TOKEN_URL = f"{ONEDRIVE_AUTHORITY}/token"
ONEDRIVE_SCOPE = "Files.Read offline_access"
ONEDRIVE_DRIVE_URL = "https://graph.microsoft.com/v1.0/me/drive"


def _redirect_code(result, expected_state):
    """(code, error) from the redirect query. The code is used only when `state` matches."""
    got = (result.get("state") or [""])[0]
    if not got or not secrets.compare_digest(got.encode(), expected_state.encode()):
        return None, "Sign-in response did not match this request (state check failed). Try again."
    code = (result.get("code") or [None])[0]
    if not code:
        return None, "No authorization code received (timed out or denied)."
    return code, None


def _oauth_error_text(resp):
    """Short error from a token endpoint: the error code only, never the body (it can echo
    the authorization code or a token)."""
    try:
        err = resp.json().get("error")
    except (ValueError, AttributeError):  # not JSON, or JSON that is not an object
        err = None
    # OAuth error codes are short ASCII words (invalid_grant); anything else is not shown.
    ok = isinstance(err, str) and re.fullmatch(r"[A-Za-z0-9_.\-]{1,64}", err)
    return f"HTTP {resp.status_code}" + (f" ({err})" if ok else "")


def onedrive_connect(account_key):
    creds = load_app_credentials().get("onedrive")
    if not creds or not creds.get("client_id"):
        return False, "No OneDrive Client ID saved yet."
    client_id = creds["client_id"]
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "response_mode": "query",
        "scope": ONEDRIVE_SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    webbrowser.open(f"{ONEDRIVE_AUTH_URL}?{urllib.parse.urlencode(params)}")
    code, error = _redirect_code(_wait_for_redirect(REDIRECT_PORT), state)
    if error:
        return False, error

    resp = requests.post(ONEDRIVE_TOKEN_URL, data={
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
        "scope": ONEDRIVE_SCOPE,
    }, timeout=20)
    if resp.status_code != 200:
        return False, f"Token exchange failed: {_oauth_error_text(resp)}"
    refresh_token = resp.json().get("refresh_token")
    if not refresh_token:
        return False, "Microsoft did not return a refresh token (is offline_access granted?)."
    _set_token_entry(account_key, {"provider": "onedrive", "refresh_token": refresh_token})
    return True, None


def _onedrive_access_token(account_key):
    """Access token for the account. Holds the account's refresh lock across read, refresh and
    store, so a second caller waits and then sends the rotated token."""
    with _refresh_lock(account_key):
        entry = load_tokens().get(account_key)
        if not entry:
            raise RuntimeError("OneDrive account is not connected.")
        creds = load_app_credentials().get("onedrive") or {}
        resp = requests.post(ONEDRIVE_TOKEN_URL, data={
            "client_id": creds.get("client_id", ""),
            "grant_type": "refresh_token",
            "refresh_token": entry["refresh_token"],
            "scope": ONEDRIVE_SCOPE,
        }, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        new_rt = data.get("refresh_token")
        if new_rt and new_rt != entry["refresh_token"]:
            _store_refresh_token(account_key, new_rt)
        return data["access_token"]


def onedrive_quota(account_key):
    """Returns Quota(used, total_or_None) as OneDrive reports it, or raises on error."""
    if not load_tokens().get(account_key):
        return None
    access_token = _onedrive_access_token(account_key)
    resp = requests.get(
        ONEDRIVE_DRIVE_URL,
        params={"$select": "quota"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    resp.raise_for_status()
    q = resp.json().get("quota") or {}
    used = int(q.get("used", 0))
    # Only an absent key means "no limit" (None). A total of 0, or one that is not a
    # positive number, is "not reported" (0): never shown as an unlimited plan.
    total = None
    if "total" in q:
        try:
            total = max(int(q["total"]), 0)
        except (TypeError, ValueError, OverflowError):
            total = 0
    return Quota(used, total)


# ----------------------------------------------------------------------------
# Provider registry. One entry per provider; the app's provider lists, credential
# form, mount detection and dispatch all read it. URLs are literals here and are
# the only URLs the app opens for a provider (never one from an API response).
# Functions are looked up by name at call time so tests can patch them.
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    mount_prefix: str | None  # CloudStorage folder name prefix, case-insensitive
    web_url: str
    # (field in app_credentials.json, form label, is_secret)
    credential_fields: tuple = ()
    connect: str | None = None  # function names in this module
    quota: str | None = None
    account_email: str | None = None
    has_quota: bool = True
    no_quota_text: str = ""  # fixed tile text when has_quota is False


PROVIDERS = {
    "google": Provider(
        "google", "Google Drive", "GoogleDrive", "https://drive.google.com/",
        credential_fields=(("client_id", "Google Client ID:", False),
                           ("client_secret", "Google Client Secret:", True)),
        connect="google_connect", quota="google_quota",
    ),
    "dropbox": Provider(
        "dropbox", "Dropbox", "Dropbox", "https://www.dropbox.com/home",
        credential_fields=(("app_key", "Dropbox App Key:", False),
                           ("app_secret", "Dropbox App Secret:", True)),
        connect="dropbox_connect", quota="dropbox_quota",
        account_email="dropbox_account_email",
    ),
    "onedrive": Provider(
        "onedrive", "OneDrive", "OneDrive", "https://onedrive.live.com/",
        credential_fields=(("client_id", "OneDrive Client ID:", False),),
        connect="onedrive_connect", quota="onedrive_quota",
    ),
    # No public quota API: link-only tile (no bar, no number, no gauge).
    "proton": Provider(
        "proton", "Proton Drive", "ProtonDrive", "https://drive.proton.me/", has_quota=False,
        no_quota_text="No quota available (Proton has no public API)",
    ),
    # iCloud keeps its own tile (ICloudTile); the registry supplies only its link.
    "icloud": Provider(
        "icloud", "iCloud Drive", None, "https://www.icloud.com/iclouddrive/", has_quota=False,
    ),
}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def link_only_providers():
    """Providers that can be added by hand as a link-only tile (no OAuth, no quota)."""
    return [p for p in PROVIDERS.values() if not p.has_quota and p.mount_prefix]


def web_link(provider, account=None):
    """The provider's page from the registry, or None. Google gets `?authuser=<email>` when the
    tile's account is a plain email; nothing else from outside the registry enters the URL."""
    p = PROVIDERS.get(provider)
    if p is None:
        return None
    if provider == "google" and account and _EMAIL_RE.fullmatch(account):
        return f"{p.web_url}?authuser={urllib.parse.quote(account, safe='')}"
    return p.web_url


def _call(func_name, *args):
    return globals()[func_name](*args)


def quota_providers():
    """Providers whose account quota can be read, in registry order."""
    return [p for p in PROVIDERS.values() if p.has_quota and p.connect]


def provider_for_name(name):
    lower = name.lower()
    for p in PROVIDERS.values():
        if p.mount_prefix and lower.startswith(p.mount_prefix.lower()):
            return p.key
    return None


def connect(provider, account_key):
    p = PROVIDERS.get(provider)
    if p is None or not p.connect:
        return False, f"Unknown provider: {provider}"
    return _call(p.connect, account_key)


def account_email(provider, account_key):
    """The account's email where the provider has a call for it, else None."""
    p = PROVIDERS.get(provider)
    if p is None or not p.account_email:
        return None
    return _call(p.account_email, account_key)


def quota(account_key):
    entry = load_tokens().get(account_key)
    if not entry:
        return None
    p = PROVIDERS.get(entry.get("provider"))
    if p is None or not p.quota:
        return None
    return _call(p.quota, account_key)
