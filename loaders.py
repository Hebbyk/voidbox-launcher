"""
mc_launcher.loaders — Fabric and Quilt loader installation.

(NeoForge/Forge are NOT here — they need a much heavier installer-processor
pipeline that actually runs bytecode-patching steps, not just a version merge.
That's a separate, dedicated piece of work.)

Both Fabric and Quilt hand back a ready "loader profile" that inherits from a
vanilla version. This module fetches that, merges it with the vanilla version
info core.py already knows how to fetch, and hands back a version_info dict
that core.py's existing pipeline (ensure_libraries/build_launch_command/
prepare_and_launch) can use completely unchanged.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

import core

FABRIC_META = "https://meta.fabricmc.net/v2/versions/loader"
QUILT_META = "https://meta.quiltmc.org/v3/versions/loader"


class LoaderError(Exception):
    pass


def _fetch_json(url: str) -> dict | list:
    try:
        with urllib.request.urlopen(url) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise LoaderError(f"Loader meta request failed ({e.code}): {url}") from None


def _extract_version(entry: dict) -> str:
    """Handles both response shapes seen across these APIs: version nested
    under a 'loader' sub-object, or flat on the entry itself."""
    return entry.get("loader", entry).get("version", "")


def _pick_stable_version(versions: list[dict]) -> str:
    """Prefer a build that doesn't look like a pre-release over just taking
    the newest entry — Quilt's (and possibly Fabric's) build list interleaves
    beta/alpha/rc builds with stable ones, so 'first in the list' isn't
    reliably 'latest stable'. This is what bit us: 'latest' picked a beta
    build that crashed on a stale Mixin service registration."""
    for entry in versions:
        version_str = _extract_version(entry)
        looks_prerelease = any(tag in version_str.lower()
                                for tag in ("beta", "alpha", "rc", "pre"))
        if version_str and not looks_prerelease:
            return version_str
    # Nothing looked stable — fall back to newest rather than failing outright
    return _extract_version(versions[0])


def _get_knot_profile(meta_base: str, minecraft_version: str, loader_version: str) -> dict:
    mc = urllib.parse.quote(minecraft_version)
    if loader_version == "latest":
        versions = _fetch_json(f"{meta_base}/{mc}")
        if not versions:
            raise LoaderError(f"No loader builds found for Minecraft {minecraft_version}")
        loader_version = _pick_stable_version(versions)
        print(f"[loaders] 'latest' resolved to {loader_version}")
    lv = urllib.parse.quote(loader_version)
    return _fetch_json(f"{meta_base}/{mc}/{lv}/profile/json")


def get_fabric_profile(minecraft_version: str, loader_version: str = "latest") -> dict:
    return _get_knot_profile(FABRIC_META, minecraft_version, loader_version)


def get_quilt_profile(minecraft_version: str, loader_version: str = "latest") -> dict:
    return _get_knot_profile(QUILT_META, minecraft_version, loader_version)


def merge_with_vanilla(loader_profile: dict) -> dict:
    """Combines a Fabric/Quilt profile with its vanilla base into one
    version_info dict, ready for core.py's existing launch pipeline."""
    vanilla_version = loader_profile.get("inheritsFrom")
    if not vanilla_version:
        raise LoaderError("Loader profile has no 'inheritsFrom' field — unexpected format")
    vanilla_info = core.get_version_info(vanilla_version)

    merged = dict(vanilla_info)
    merged["id"] = loader_profile.get("id", vanilla_info["id"])
    merged["mainClass"] = loader_profile["mainClass"]
    # Fabric/Quilt's own libraries use an older maven-coordinate format —
    # core.ensure_libraries() has been taught to handle both this and Mojang's
    # own direct-download format in the same classpath-building pass.
    merged["libraries"] = list(vanilla_info.get("libraries", [])) + \
        list(loader_profile.get("libraries", []))

    vanilla_args = vanilla_info.get("arguments", {})
    loader_args = loader_profile.get("arguments", {})
    merged["arguments"] = {
        "game": list(vanilla_args.get("game", [])) + list(loader_args.get("game", [])),
        "jvm": list(vanilla_args.get("jvm", [])) + list(loader_args.get("jvm", [])),
    }
    return merged


def install_fabric(minecraft_version: str, loader_version: str = "latest") -> dict:
    """Returns a version_info dict — pass it straight into
    core.prepare_and_launch(..., version_id=result['id'], version_info=result)"""
    return merge_with_vanilla(get_fabric_profile(minecraft_version, loader_version))


def install_quilt(minecraft_version: str, loader_version: str = "latest") -> dict:
    return merge_with_vanilla(get_quilt_profile(minecraft_version, loader_version))


if __name__ == "__main__":
    import sys
    from pathlib import Path
    if len(sys.argv) < 4:
        print("usage: py loaders.py <fabric|quilt> <minecraft_version> <username> "
              "[loader_version] [instance_dir] [java_path]")
        sys.exit(1)
    kind, mc_version, username = sys.argv[1], sys.argv[2], sys.argv[3]
    loader_version = sys.argv[4] if len(sys.argv) > 4 else "latest"
    instance_dir = Path(sys.argv[5]) if len(sys.argv) > 5 else Path("./test_instance_loader")
    java_path = sys.argv[6] if len(sys.argv) > 6 else None

    installer = install_fabric if kind == "fabric" else install_quilt
    version_info = installer(mc_version, loader_version)
    print(f"[loaders] resolved: {version_info['id']}")

    core.prepare_and_launch(instance_dir, version_info["id"], core.offline_auth(username),
                             version_info=version_info, java_path=java_path)
