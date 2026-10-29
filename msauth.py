"""
mc_launcher.msauth — Microsoft account login for PREMIUM Minecraft accounts,
using the official Minecraft Launcher's own Microsoft client ID.

Why this shape: a fresh, self-registered Azure app currently can't get approved
for Minecraft API access (Microsoft gates that behind ID@Xbox, which requires
submitting an actual game). This instead reuses the real Minecraft Launcher's
own client ID against the older "Windows Live" login system (login.live.com) —
a different, older auth surface than a custom Azure app would use, and one
that's already approved since it *is* the official launcher's identity.

Heads up (read this): a client ID for a public/native app isn't a secret by
design — this is the same technique several well-known open source Minecraft
tools use (e.g. prismarine-auth's default "live" flow). But it does mean your
login requests present themselves to Microsoft as the official launcher,
which sits in a gray area against the letter of their API terms even though
it only ever touches your own real account (no fraud, no one else's account).
Real-world reports (as of testing this) say it still works but with two
quirks: you have to grab the code from the redirect URL quickly before it
bounces to another page, and it must be done in a real browser — Microsoft
rejects logins coming from an embedded/automated browser view.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as uuidlib
import webbrowser
from pathlib import Path

CLIENT_ID = "00000000402B5328"  # the real Minecraft Launcher's own client ID
REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"
SCOPE = "service::user.auth.xboxlive.com::MBI_SSL"

AUTHORIZE_URL = "https://login.live.com/oauth20_authorize.srf"
TOKEN_URL = "https://login.live.com/oauth20_token.srf"
XBL_AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_AUTH_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_ENTITLEMENTS_URL = "https://api.minecraftservices.com/entitlements/mcstore"
MC_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"

XSTS_ERRORS = {
    2148916233: "This Microsoft account has no Xbox Live profile. Log into "
                 "xbox.com once with it to create one, then try again.",
    2148916235: "Xbox Live isn't available in this account's region.",
    2148916236: "This account needs adult verification (South Korea).",
    2148916237: "This account needs adult verification (South Korea).",
    2148916238: "This is a child account and must be added to a Family by an "
                 "adult before it can sign in.",
}


class MSAuthError(Exception):
    pass


def _post_form(url: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise MSAuthError(body or f"HTTP {e.code}") from None


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", "Accept": "application/json",
    }, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise MSAuthError(body or f"HTTP {e.code}") from None


# ---------------------------------------------------------------------------
# Step 1: interactive login (manual browser + paste-back, no local server)
# ---------------------------------------------------------------------------

def get_login_url() -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def parse_code_from_redirect(redirect_url: str) -> str:
    """Pulls the `code` query param out of the URL the user pastes back.
    Raises a clear error if they pasted an error page or the wrong thing."""
    parsed = urllib.parse.urlparse(redirect_url.strip())
    query = urllib.parse.parse_qs(parsed.query)
    if "code" in query:
        return query["code"][0]
    if "error" in query:
        desc = query.get("error_description", query["error"])[0]
        raise MSAuthError(f"Microsoft login failed: {desc}")
    raise MSAuthError(
        "Couldn't find a 'code' parameter in that URL. Make sure you copied "
        "the address bar right after logging in (it happens fast, before the "
        "page redirects again)."
    )


def exchange_code_for_ms_tokens(code: str) -> dict:
    """Returns {access_token, refresh_token, ...}."""
    return _post_form(TOKEN_URL, {
        "client_id": CLIENT_ID,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "scope": SCOPE,
    })


def refresh_ms_tokens(refresh_token: str) -> dict:
    return _post_form(TOKEN_URL, {
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": SCOPE,
    })


# ---------------------------------------------------------------------------
# Steps 2-3: Xbox Live token chain
# ---------------------------------------------------------------------------

def xbl_authenticate(ms_access_token: str) -> tuple[str, str]:
    """Returns (xbl_token, user_hash). Note: unlike the modern Azure-app flow,
    this legacy 'live' flow passes the token raw — no 'd=' prefix."""
    resp = _post_json(XBL_AUTH_URL, {
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": ms_access_token,
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT",
    })
    return resp["Token"], resp["DisplayClaims"]["xui"][0]["uhs"]


def xsts_authenticate(xbl_token: str) -> tuple[str, str]:
    """Returns (xsts_token, user_hash)."""
    try:
        resp = _post_json(XSTS_AUTH_URL, {
            "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_token]},
            "RelyingParty": "rp://api.minecraftservices.com/",
            "TokenType": "JWT",
        })
    except MSAuthError as e:
        try:
            err = json.loads(str(e))
            code = err.get("XErr")
            raise MSAuthError(XSTS_ERRORS.get(code, f"XSTS error {code}: {err}")) from None
        except (json.JSONDecodeError, TypeError):
            raise
    return resp["Token"], resp["DisplayClaims"]["xui"][0]["uhs"]


# ---------------------------------------------------------------------------
# Steps 4-5: Minecraft services
# ---------------------------------------------------------------------------

def minecraft_login(user_hash: str, xsts_token: str) -> str:
    resp = _post_json(MC_LOGIN_URL, {"identityToken": f"XBL3.0 x={user_hash};{xsts_token}"})
    return resp["access_token"]


def owns_minecraft(mc_access_token: str) -> bool:
    req = urllib.request.Request(MC_ENTITLEMENTS_URL,
                                  headers={"Authorization": f"Bearer {mc_access_token}"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return len(data.get("items", [])) > 0


def get_profile(mc_access_token: str) -> dict:
    req = urllib.request.Request(MC_PROFILE_URL,
                                  headers={"Authorization": f"Bearer {mc_access_token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise MSAuthError("This Microsoft account doesn't own Minecraft.") from None
        raise
    return {"uuid": str(uuidlib.UUID(data["id"])), "username": data["name"]}


# ---------------------------------------------------------------------------
# High-level entry points
# ---------------------------------------------------------------------------

def _login_window_command(result_file: str) -> list[str]:
    """How to start the sign-in window as its own process. Packaged app: the
    launcher's own exe with a flag (gui.py handles it before loading any UI).
    From source: this file, run as a script."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--ms-login-window", result_file]
    return [sys.executable, str(Path(__file__).resolve()), "--ms-login-window", result_file]


def run_login_window(result_file: str, width: int = 500, height: int = 650) -> None:
    """Runs in the CHILD process (see authenticate_embedded): opens the sign-in
    window, watches which page it navigates to, and writes the redirect URL
    (or an error) to result_file as JSON. pywebview insists on running on the
    main thread of its process, which is why this is its own process — the
    launcher's main thread belongs to the app window."""
    result = {}
    try:
        import webview

        def on_loaded():
            current = window.get_current_url()
            if current and current.startswith(REDIRECT_URI):
                result["url"] = current
                window.destroy()

        window = webview.create_window("Sign in with Microsoft", get_login_url(),
                                        width=width, height=height)
        window.events.loaded += on_loaded
        webview.start()  # blocks until the window closes
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    Path(result_file).write_text(json.dumps(result), encoding="utf-8")


def authenticate_embedded(width: int = 500, height: int = 650, timeout: int = 600) -> dict:
    """Fully automatic login: opens a small embedded browser window (via
    pywebview), watches which page it navigates to, and grabs the code the
    instant it lands on the redirect page — no copying, no pasting, no
    external browser. The window closes itself once done.

    You still see and use the real Microsoft login page and type your own
    password by hand — this only watches where the page goes afterward,
    it doesn't automate the login form itself (that's the part that gets
    flagged/rejected by Microsoft; passively watching navigation doesn't).

    The window lives in a separate process (pywebview must own a process's
    main thread), so this is safe to call from a background thread.
    Requires: pip install pywebview
    """
    fd, result_file = tempfile.mkstemp(prefix="voidbox-msa-", suffix=".json")
    os.close(fd)
    returncode = 0
    try:
        try:
            returncode = subprocess.run(_login_window_command(result_file), timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            raise MSAuthError("The Microsoft login window timed out.") from None
        except OSError as e:
            raise MSAuthError(f"Couldn't open the Microsoft login window: {e}") from None
        try:
            result = json.loads(Path(result_file).read_text(encoding="utf-8") or "{}")
        except (OSError, ValueError):
            result = {}
    finally:
        try:
            os.unlink(result_file)
        except OSError:
            pass

    if "url" not in result:
        if result.get("error"):
            raise MSAuthError(f"Couldn't open the Microsoft login window: {result['error']}")
        if returncode != 0:
            raise MSAuthError(f"The Microsoft login window closed unexpectedly (exit code {returncode}).")
        raise MSAuthError("Login window was closed before signing in completed.")

    code = parse_code_from_redirect(result["url"])
    ms_tokens = exchange_code_for_ms_tokens(code)
    return _finish_login(ms_tokens)


def authenticate() -> dict:
    """Full interactive login: prints a URL, waits for you to paste back the
    redirect, then completes the chain. Returns an auth dict compatible with
    core.prepare_and_launch, plus 'ms_refresh_token' for silent re-login."""
    print(f"\nOpen this in a real browser (not an embedded one) and log in:\n"
          f"{get_login_url()}\n")
    print("After logging in, you'll land on a mostly-blank page within a few "
          "seconds — copy its full URL from the address bar RIGHT AWAY, "
          "before it redirects again.\n")
    redirect_url = input("Paste that URL here: ")
    code = parse_code_from_redirect(redirect_url)
    ms_tokens = exchange_code_for_ms_tokens(code)
    return _finish_login(ms_tokens)


def authenticate_auto(timeout: int = 180) -> dict:
    """Same login, minus the manual paste: opens your browser for you, then
    watches the clipboard so the moment you copy the redirect URL (Ctrl+A,
    Ctrl+C on the address bar), it's picked up automatically. You still have
    to do that one copy yourself — Microsoft's redirect page is fixed for
    this client ID (it's their app, not ours), so there's no listener we can
    register to skip it entirely."""
    url = get_login_url()
    print("Opening your browser to log in...")
    if not webbrowser.open(url):
        print(f"Couldn't auto-open a browser — open this manually:\n{url}")
    print("The moment the page goes blank after logging in, select the "
          "address bar (Ctrl+A) and copy it (Ctrl+C). I'll pick it up "
          "automatically from there...")

    redirect_url = _wait_for_redirect_in_clipboard(timeout)
    code = parse_code_from_redirect(redirect_url)
    ms_tokens = exchange_code_for_ms_tokens(code)
    return _finish_login(ms_tokens)


def _wait_for_redirect_in_clipboard(timeout: int) -> str:
    try:
        import tkinter
    except ImportError:
        raise MSAuthError(
            "Clipboard watching needs tkinter, which isn't available in this "
            "Python install. Use authenticate() instead (manual paste)."
        ) from None

    root = tkinter.Tk()
    root.withdraw()
    seen = set()
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            try:
                text = root.clipboard_get()
            except tkinter.TclError:
                text = None
            if text and "oauth20_desktop.srf" in text and text not in seen:
                return text
            root.update()
            time.sleep(0.5)
    finally:
        root.destroy()
    raise MSAuthError(
        "Timed out waiting for the login redirect URL on your clipboard. "
        "Make sure you copied the address bar right after logging in."
    )


def authenticate_with_refresh_token(refresh_token: str) -> dict:
    """Silent re-login using a refresh token from a previous authenticate() call."""
    ms_tokens = refresh_ms_tokens(refresh_token)
    return _finish_login(ms_tokens)


def _finish_login(ms_tokens: dict) -> dict:
    xbl_token, _ = xbl_authenticate(ms_tokens["access_token"])
    xsts_token, user_hash = xsts_authenticate(xbl_token)
    mc_access_token = minecraft_login(user_hash, xsts_token)

    if not owns_minecraft(mc_access_token):
        raise MSAuthError("This Microsoft account doesn't own Minecraft.")

    profile = get_profile(mc_access_token)
    return {
        "access_token": mc_access_token,
        "uuid": profile["uuid"],
        "username": profile["username"],
        "user_type": "msa",
        "ms_refresh_token": ms_tokens.get("refresh_token"),
    }



# ---------------------------------------------------------------------------
# Session caching — makes login automatic after the first time.
# Stored in Windows Credential Manager (via keyring), the same vault your
# browser and Windows itself use for saved passwords. Requires:
#     py -m pip install keyring
# ---------------------------------------------------------------------------

KEYRING_SERVICE = "mc_launcher_msa"
KEYRING_USERNAME = "refresh_token"


def _load_cached_refresh_token() -> str | None:
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except ImportError:
        return None
    except Exception:
        return None  # no saved credential yet, or vault unavailable


def _save_refresh_token(refresh_token: str | None):
    if not refresh_token:
        return
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, refresh_token)
    except ImportError:
        print("[msauth] keyring isn't installed, so the session can't be saved — "
              "run: py -m pip install keyring")


def get_auth() -> dict:
    """The function to actually call day-to-day. Tries a silent refresh using
    the session saved in Windows Credential Manager first; only prompts for
    login if there's no saved session yet or the refresh fails (expired after
    ~90 days unused, or revoked). Always re-saves the latest refresh token."""
    cached = _load_cached_refresh_token()
    if cached:
        try:
            print("[msauth] found a saved session, logging in silently (no browser needed)...")
            auth = authenticate_with_refresh_token(cached)
            _save_refresh_token(auth.get("ms_refresh_token"))
            print(f"[msauth] signed in as {auth['username']}")
            return auth
        except MSAuthError:
            print("[msauth] Saved session expired or was revoked — logging in fresh.")

    auth = authenticate_embedded()
    _save_refresh_token(auth.get("ms_refresh_token"))
    return auth


def try_silent_auth() -> dict | None:
    """Like get_auth(), but NEVER falls through to an interactive login —
    returns None instead if there's no usable saved session. For checking
    at app startup, where popping a login window uninvited would be wrong."""
    cached = _load_cached_refresh_token()
    if not cached:
        return None
    try:
        print("[msauth] found a saved session, logging in silently (no browser needed)...")
        auth = authenticate_with_refresh_token(cached)
        _save_refresh_token(auth.get("ms_refresh_token"))
        print(f"[msauth] signed in as {auth['username']}")
        return auth
    except MSAuthError:
        return None


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--ms-login-window":
        run_login_window(sys.argv[2])  # child-process mode, started by authenticate_embedded()
        sys.exit(0)
    result = get_auth()
    print(json.dumps(result, indent=2))
