"""#14 - send CurseForge requests through your relay (no key inside the app).
Run once from C:\\MCLauncher, AFTER cf_key_patch.py:   py relay_patch.py
Edits settings.py, search.py, curseforge.py, mod_updater.py, backfill_manifest.py, voidbox.spec, build.ps1
(writes .relay.bak first), creates cf_net.py and a private _relay.py, and adds _relay.py to .git\\info\\exclude.
If any file is not what is expected, NOTHING is changed."""
import os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))

CF_NET = '''"""Where CurseForge requests go.

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
'''

RELAY_TEMPLATE = '''# Private: the address of your CurseForge relay, e.g. URL = "https://relay.example.com"
# Never commit this file (it is in .git/info/exclude). Empty = talk to CurseForge directly.
URL = ""
'''

# file -> list of (old, new, expected_count)
EDITS = {
    "settings.py": [
        ('    return _get("curseforge_api_key") or _builtin_curseforge_key()\n',
         '    own = _get("curseforge_api_key")\n'
         '    if own:\n'
         '        return own\n'
         '    import cf_net\n'
         '    if cf_net.relay_url():\n'
         '        return cf_net.RELAY_KEY   # the relay adds the real key; nothing secret ships in the app\n'
         '    return _builtin_curseforge_key()\n', 1),
    ],
    "search.py": [
        ('\nimport core\n', '\nimport cf_net\nimport core\n', 1),
        ('{CURSEFORGE_API}', '{cf_net.base()}', 4),
    ],
    "curseforge.py": [
        ('from packs import ResolvedFile, ResolvedPack\n', 'import cf_net\nfrom packs import ResolvedFile, ResolvedPack\n', 1),
        ('url = f"{API_BASE}{path}"', 'url = f"{cf_net.base()}{path}"', 1),
    ],
    "mod_updater.py": [
        ('\nimport core\n', '\nimport cf_net\nimport core\n', 1),
        ('{CURSEFORGE}/fingerprints', '{cf_net.base()}/fingerprints', 1),
    ],
    "backfill_manifest.py": [
        ('\nimport export_packwiz', '\nimport cf_net\nimport export_packwiz', 1),
        ('_post_json(CURSEFORGE_FINGERPRINTS_URL,', '_post_json(cf_net.base() + "/fingerprints",', 1),
    ],
    "voidbox.spec": [
        ('    print("[spec] NOTE: no _cfk.py - this build has NO built-in CurseForge key (run make_key.py first)")\n',
         '    print("[spec] NOTE: no _cfk.py - this build has NO built-in CurseForge key (run make_key.py first)")\n'
         '\n# CurseForge relay address: _relay.py is private (never in git); cf_net.py imports it inside try/except.\n'
         'if os.path.exists(os.path.join(HERE, "_relay.py")):\n'
         '    hiddenimports += ["_relay"]\n'
         'else:\n'
         '    print("[spec] NOTE: no _relay.py - this build talks to CurseForge directly")\n', 1),
    ],
    "build.ps1": [
        ('"voidbox.spec", "voidbox.wxs"', '"voidbox.spec", "cf_net.py", "voidbox.wxs"', 1),
        ('    Write-Host "NOTE: _cfk.py not found - this build will have no built-in CurseForge key (run: py make_key.py)" -ForegroundColor Yellow\n}\n',
         '    Write-Host "NOTE: _cfk.py not found - this build will have no built-in CurseForge key (run: py make_key.py)" -ForegroundColor Yellow\n}\n'
         '\nif (-not (Test-Path "_relay.py")) {\n'
         '    Write-Host "NOTE: _relay.py not found - this build will talk to CurseForge directly (put the relay address in _relay.py)" -ForegroundColor Yellow\n}\n', 1),
    ],
}

def main():
    # preconditions
    cf_path = os.path.join(HERE, "settings.py")
    if not os.path.exists(cf_path):
        sys.exit("settings.py not found. Nothing changed.")
    with open(cf_path, "r", encoding="utf-8") as f:
        if "has_own_curseforge_key" not in f.read():
            sys.exit("Run cf_key_patch.py first (settings.py has no has_own_curseforge_key). Nothing changed.")
    if os.path.exists(os.path.join(HERE, "cf_net.py")):
        sys.exit("cf_net.py already exists - looks like this patch was already applied. Nothing changed.")
    new, crlf = {}, {}
    for name, edits in EDITS.items():
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            sys.exit(f"{name} not found. Nothing changed.")
        with open(p, "r", encoding="utf-8", newline="") as f:
            raw = f.read()
        crlf[name] = "\r\n" in raw
        text = raw.replace("\r\n", "\n")
        for old, rep, n in edits:
            if text.count(old) != n:
                sys.exit(f"{name}: expected {n} match(es) of\n  {old[:70]!r}\nbut found {text.count(old)}. Nothing changed.")
            text = text.replace(old, rep)
        new[name] = text
    for name, text in new.items():
        p = os.path.join(HERE, name)
        shutil.copy2(p, p + ".relay.bak")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace("\n", "\r\n") if crlf[name] else text)
        print("patched", name)
    with open(os.path.join(HERE, "cf_net.py"), "w", encoding="utf-8", newline="") as f:
        f.write(CF_NET)
    print("created cf_net.py")
    rp = os.path.join(HERE, "_relay.py")
    if not os.path.exists(rp):
        with open(rp, "w", encoding="utf-8", newline="") as f:
            f.write(RELAY_TEMPLATE)
        print("created _relay.py (empty address - fill it in later)")
    ex = os.path.join(HERE, ".git", "info", "exclude")
    if os.path.isdir(os.path.dirname(ex)):
        cur = open(ex, "r", encoding="utf-8").read() if os.path.exists(ex) else ""
        if "_relay.py" not in cur.split():
            with open(ex, "a", encoding="utf-8") as f:
                f.write(("" if cur.endswith("\n") or not cur else "\n") + "_relay.py\n")
            print("added _relay.py to .git/info/exclude")
    print("Done. Nothing changes until _relay.py has an https:// address.")

main()
