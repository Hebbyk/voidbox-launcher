"""
mc_launcher.forge — Forge and NeoForge installation, STAGE 1 of 2.

This stage: resolve which Forge/NeoForge build to use, download its
installer jar, and pull version.json + install_profile.json out of it.

STAGE 2 (separate, not built yet): merge install_profile.json's libraries
into the launch pipeline and actually RUN its "processors" — small Java
programs that patch together a working client jar. That's the genuinely
hard part; this stage alone is not enough to launch a Forge/NeoForge
instance yet, just to inspect what one needs.
"""
import json
import re
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

FORGE_PROMOTIONS_URL = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
FORGE_MAVEN_BASE = "https://maven.minecraftforge.net/net/minecraftforge/forge"
NEOFORGE_META_URL = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
NEOFORGE_MAVEN_BASE = "https://maven.neoforged.net/releases/net/neoforged/neoforge"


class ForgeError(Exception):
    pass


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) mc_launcher/0.1"


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise ForgeError(f"Request failed ({e.code}): {url}") from None


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise ForgeError(f"Request failed ({e.code}): {url}") from None


def _parse_maven_versions(xml_text: str) -> list[str]:
    """maven-metadata.xml is simple enough not to need a real XML parser."""
    return re.findall(r"<version>(.*?)</version>", xml_text)


def get_forge_version(minecraft_version: str, choice: str = "recommended") -> str:
    """choice: 'recommended', 'latest', or an exact Forge version string."""
    if choice not in ("recommended", "latest"):
        return choice
    promos = _fetch_json(FORGE_PROMOTIONS_URL)["promos"]
    version = promos.get(f"{minecraft_version}-{choice}")
    if not version and choice == "recommended":
        # not every MC version has a 'recommended' build, only 'latest'
        version = promos.get(f"{minecraft_version}-latest")
    if not version:
        raise ForgeError(f"No Forge build found for Minecraft {minecraft_version}")
    return version


def neoforge_prefix(minecraft_version: str) -> str:
    """Which NeoForge versions belong to a Minecraft version.
    1.x:  1.21.1 -> '21.1.'   1.21 -> '21.0.'   1.21.11 -> '21.11.'
    26.x: Minecraft 26.1 -> '26.1.0.'   26.1.2 -> '26.1.2.'  (NeoForge keeps the full version at the start from
          26.1 on; the 26.x rule comes from NeoForge's own announcement, not from a build I could launch)."""
    parts = minecraft_version.split(".")
    if parts[0] == "1" and len(parts) >= 2:
        return f"{parts[1]}.{parts[2] if len(parts) > 2 else '0'}."
    if parts[0].isdigit() and int(parts[0]) >= 26 and len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}.{parts[2] if len(parts) > 2 else '0'}."
    raise ForgeError(f"Can't derive a NeoForge version prefix from '{minecraft_version}'")


def get_neoforge_version(minecraft_version: str, choice: str = "latest") -> str:
    """choice: 'latest', or an exact NeoForge version string. NeoForge doesn't
    publish a 'recommended' designation the way Forge does."""
    if choice not in ("latest", "recommended"):
        return choice
    prefix = neoforge_prefix(minecraft_version)

    matching = [v for v in _parse_maven_versions(_fetch_text(NEOFORGE_META_URL))
                if v.startswith(prefix)]
    if not matching:
        raise ForgeError(f"No NeoForge build found for Minecraft {minecraft_version}")
    stable = [v for v in matching if not any(t in v.lower() for t in ("beta", "alpha", "rc"))]
    return (stable or matching)[-1]  # maven-metadata lists oldest -> newest


def forge_installer_url(minecraft_version: str, forge_version: str) -> str:
    full = f"{minecraft_version}-{forge_version}"
    return f"{FORGE_MAVEN_BASE}/{full}/forge-{full}-installer.jar"


def neoforge_installer_url(neoforge_version: str) -> str:
    return f"{NEOFORGE_MAVEN_BASE}/{neoforge_version}/neoforge-{neoforge_version}-installer.jar"


def download_installer(url: str, cache_dir: Path) -> Path:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / url.rsplit("/", 1)[1]
    if not dest.exists() or not zipfile.is_zipfile(dest):
        if dest.exists():
            dest.unlink()  # corrupt/incomplete leftover
        print(f"[forge] downloading installer: {dest.name}")
        tmp = dest.with_suffix(".jar.part")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req) as resp, open(tmp, "wb") as out:
            out.write(resp.read())
        if not zipfile.is_zipfile(tmp):
            tmp.unlink(missing_ok=True)
            raise ForgeError(f"Downloaded installer isn't a valid jar: {url}")
        tmp.rename(dest)
    return dest


def extract_installer_metadata(installer_jar: Path) -> tuple[dict, dict]:
    """Returns (version_json, install_profile_json) read straight out of the
    installer jar — no extraction to disk needed for just these two files."""
    with zipfile.ZipFile(installer_jar) as zf:
        version_json = json.loads(zf.read("version.json"))
        install_profile = json.loads(zf.read("install_profile.json"))
    return version_json, install_profile


# ---------------------------------------------------------------------------
# Stage 3: tying it all together into something bootable
# ---------------------------------------------------------------------------

def prepare_forge(mc_version: str, kind: str = "forge", choice: str | None = None,
                   java_path: str | None = None) -> tuple[dict, Path]:
    """Does everything through having a bootable version_info + finished
    patched client jar. Returns (merged_version_info, patched_client_jar_path)
    — pass both into core.prepare_and_launch()'s version_info and
    client_jar_override params to actually launch."""
    import core
    import java_finder
    import loaders  # reuses merge_with_vanilla() — same inheritsFrom mechanism as Fabric/Quilt
    import forge_processors

    choice = choice or ("recommended" if kind == "forge" else "latest")
    if kind == "forge":
        loader_version = get_forge_version(mc_version, choice)
        url = forge_installer_url(mc_version, loader_version)
    else:
        loader_version = get_neoforge_version(mc_version, choice)
        url = neoforge_installer_url(loader_version)
    print(f"[forge] resolved {kind} version: {loader_version}")

    shared = core.get_shared_cache_dir()
    installer_jar = download_installer(url, shared / "forge_installers")
    version_json, install_profile = extract_installer_metadata(installer_jar)

    merged_version_info = loaders.merge_with_vanilla(version_json)

    versions_dir = shared / "versions"
    libs_dir = shared / "libraries"
    natives_dir = shared / "natives" / mc_version

    vanilla_info = core.get_version_info(mc_version)
    if java_path is None:
        java_path = java_finder.resolve_java_path(vanilla_info)

    print("[forge] downloading vanilla client jar...")
    vanilla_client_jar = core.ensure_client_jar(vanilla_info, versions_dir)

    print("[forge] downloading install_profile's own libraries (installer tools)...")
    core.ensure_libraries(install_profile, libs_dir, natives_dir)

    print("[forge] downloading version.json's own runtime libraries...")
    core.ensure_libraries(merged_version_info, libs_dir, natives_dir)

    install_root = shared / "forge_work" / merged_version_info["id"]
    install_root.mkdir(parents=True, exist_ok=True)

    ctx = forge_processors.InstallContext(
        libraries_dir=libs_dir, root=install_root, installer_jar=installer_jar,
        minecraft_jar=vanilla_client_jar, side="client",
    )
    forge_processors.run_all_processors(install_profile, ctx, java_path)

    patched_raw = install_profile["data"]["PATCHED"]["client"]
    patched_jar = Path(ctx.resolve_data_value(patched_raw))
    if not patched_jar.exists():
        raise ForgeError(f"Processor pipeline finished but the expected output jar "
                          f"is missing: {patched_jar}")
    print(f"[forge] patched client jar ready: {patched_jar}")

    return merged_version_info, patched_jar


def install_and_launch(instance_root, mc_version: str, auth: dict, kind: str = "forge",
                        choice: str | None = None, java_path: str | None = None,
                        memory_mb: int = 4096):
    """The one-call entry point: resolves, downloads, patches, and launches."""
    import core
    merged_version_info, patched_jar = prepare_forge(mc_version, kind, choice, java_path)
    core.prepare_and_launch(
        instance_root, merged_version_info["id"], auth, memory_mb=memory_mb,
        version_info=merged_version_info, java_path=java_path,
        client_jar_override=patched_jar,
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("usage: py forge.py <forge|neoforge> <minecraft_version> <username> "
              "[version_choice] [instance_dir] [java_path]")
        sys.exit(1)
    kind, mc_version, username = sys.argv[1], sys.argv[2], sys.argv[3]
    choice = sys.argv[4] if len(sys.argv) > 4 else None
    instance_dir = Path(sys.argv[5]) if len(sys.argv) > 5 else Path(f"./test_instance_{kind}")
    java_path = sys.argv[6] if len(sys.argv) > 6 else None

    import core
    install_and_launch(instance_dir, mc_version, core.offline_auth(username),
                        kind=kind, choice=choice, java_path=java_path)
