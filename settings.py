"""
mc_launcher.settings — small persisted app settings: the CurseForge API key,
a saved ely.by session, and which login method was used last. Uses the same
Windows Credential Manager vault (via keyring) as msauth's Microsoft session
caching, so it's consistent with how login persistence already works there.
"""
import json

SERVICE = "mc_launcher_settings"


def _get(key: str) -> str | None:
    try:
        import keyring
        return keyring.get_password(SERVICE, key)
    except Exception:
        return None


def _set(key: str, value: str):
    try:
        import keyring
        keyring.set_password(SERVICE, key, value)
    except Exception:
        pass


def _builtin_curseforge_key() -> str | None:
    """Key baked in at build time by make_key.py (_cfk.py). None for builds without one."""
    try:
        import _cfk
        return _cfk.get() or None
    except Exception:
        return None


def get_curseforge_api_key() -> str | None:
    # A key the user pasted themselves always wins; otherwise fall back to the built-in one.
    return _get("curseforge_api_key") or _builtin_curseforge_key()


def save_curseforge_api_key(key: str):
    if key:
        _set("curseforge_api_key", key)


def get_elyby_session() -> dict | None:
    raw = _get("elyby_session")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def save_elyby_session(access_token: str, client_token: str):
    _set("elyby_session", json.dumps({"access_token": access_token, "client_token": client_token}))


def get_last_login_method() -> str | None:
    return _get("last_login_method")  # "cracked" | "premium"


def save_last_login_method(method: str):
    _set("last_login_method", method)
