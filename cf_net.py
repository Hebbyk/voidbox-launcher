"""Where CurseForge requests go.

With no key of the person's own, requests go to the relay (its address lives in the private _relay.py, which
is never in git) and the relay adds the real key on the server - so no key ships inside the app. With the
person's own key (Settings), or in a build without a relay, requests go straight to CurseForge.
"""
OFFICIAL = "https://api.curseforge.com/v1"
RELAY_KEY = "relay"   # placeholder sent as x-api-key; the relay ignores it and uses the real one


def relay_url() -> str:
    try:
        import _relay
        url = str(getattr(_relay, "URL", "") or "").strip().rstrip("/")
    except Exception:
        return ""
    return url if url.startswith("https://") else ""


def using_relay() -> bool:
    try:
        import settings
        if settings.has_own_curseforge_key():
            return False
    except Exception:
        pass
    return bool(relay_url())


def base() -> str:
    return relay_url() + "/v1" if using_relay() else OFFICIAL
