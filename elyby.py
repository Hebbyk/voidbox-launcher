"""
mc_launcher.elyby — ely.by login for skinned "cracked" accounts.

This is the same trick TLauncher uses: real offline-style play, but with an
actual skin/cape, by logging into ely.by (a free account at https://ely.by)
and telling the game to route all auth/skin lookups there via authlib-injector
(a javaagent that patches Mojang's authlib at runtime — no game files modified).

Flow:
    auth = elyby.authenticate("myEsyByUsername", "mypassword")
    jar = elyby.ensure_injector_jar(cache_dir)
    core.prepare_and_launch(instance_root, "1.20.1", auth,
                             extra_jvm_args=elyby.get_extra_jvm_args(jar))
"""
import json
import urllib.error
import urllib.request
import uuid as uuidlib
import zipfile
from pathlib import Path

AUTHENTICATE_URL = "https://authserver.ely.by/auth/authenticate"
REFRESH_URL = "https://authserver.ely.by/auth/refresh"
INJECTOR_META_URL = "https://authlib-injector.yushi.moe/artifact/latest.json"


class ElyByError(Exception):
    pass


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        try:
            err = json.loads(body)
            raise ElyByError(err.get("errorMessage") or err.get("error") or body) from None
        except json.JSONDecodeError:
            raise ElyByError(body or f"HTTP {e.code}") from None


def _format_uuid(raw: str) -> str:
    return str(uuidlib.UUID(raw.replace("-", "")))


def authenticate(username_or_email: str, password: str, totp: str | None = None,
                  client_token: str | None = None) -> dict:
    """Logs into ely.by. If the account has 2FA on, pass the 6-digit code as `totp`
    (ely.by wants it appended to the password as "password:123456").
    Returns an auth dict compatible with core.prepare_and_launch / build_launch_command."""
    pw = f"{password}:{totp}" if totp else password
    payload = {
        "username": username_or_email,
        "password": pw,
        "clientToken": client_token or str(uuidlib.uuid4()),
        "requestUser": True,
        "agent": {"name": "Minecraft", "version": 1},
    }
    resp = _post_json(AUTHENTICATE_URL, payload)
    profile = resp.get("selectedProfile") or next(iter(resp.get("availableProfiles", [])), None)
    if not profile:
        raise ElyByError("This ely.by account has no Minecraft profile set up")

    return {
        "access_token": resp["accessToken"],
        "client_token": resp["clientToken"],
        "uuid": _format_uuid(profile["id"]),
        "username": profile["name"],
        # "mojang" (not "msa"/"legacy") tells the client to take the online-mode
        # code path, which authlib-injector then redirects to ely.by instead of Mojang.
        "user_type": "mojang",
    }


def refresh(access_token: str, client_token: str) -> dict:
    """Get a fresh access token without re-prompting for a password."""
    resp = _post_json(REFRESH_URL, {
        "accessToken": access_token, "clientToken": client_token, "requestUser": True,
    })
    profile = resp["selectedProfile"]
    return {
        "access_token": resp["accessToken"],
        "client_token": resp["clientToken"],
        "uuid": _format_uuid(profile["id"]),
        "username": profile["name"],
        "user_type": "mojang",
    }


def ensure_injector_jar(cache_dir: Path) -> Path:
    """Downloads + caches the latest authlib-injector build. Safe to call every launch.
    Always returns an ABSOLUTE path — this jar path ends up in a -javaagent arg for a
    Java process launched with a different working directory, so a relative path here
    would silently point at the wrong file (this bit us once already)."""
    cache_dir = Path(cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(INJECTOR_META_URL) as resp:
        meta = json.loads(resp.read())
    jar_path = cache_dir / f"authlib-injector-{meta['version']}.jar"

    if jar_path.exists() and not zipfile.is_zipfile(jar_path):
        print(f"[elyby] cached {jar_path.name} is corrupt (not a valid jar) — re-downloading...")
        jar_path.unlink()

    if not jar_path.exists():
        tmp = jar_path.with_suffix(".jar.part")
        urllib.request.urlretrieve(meta["download_url"], tmp)
        if not zipfile.is_zipfile(tmp):
            tmp.unlink(missing_ok=True)
            raise ElyByError(
                f"Downloaded authlib-injector jar is not a valid zip/jar. This usually means "
                f"antivirus quarantined or truncated it mid-download — check your AV history "
                f"for {tmp.name}."
            )
        tmp.rename(jar_path)

    return jar_path


def get_extra_jvm_args(injector_jar: Path) -> list[str]:
    """'ely.by' here is a shorthand host name — authlib-injector resolves it to
    the real API root via a well-known lookup, no need to hardcode the full URL."""
    return [f"-javaagent:{injector_jar}=ely.by"]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: py elyby.py <username_or_email> <password> [totp]")
        sys.exit(1)
    totp = sys.argv[3] if len(sys.argv) > 3 else None
    result = authenticate(sys.argv[1], sys.argv[2], totp)
    print(json.dumps(result, indent=2))
