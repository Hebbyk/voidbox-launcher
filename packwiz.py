"""
mc_launcher.packwiz — imports a packwiz pack from wherever its pack.toml is
hosted (a GitHub raw link, a `packwiz serve` URL, etc.) — that's how packwiz
packs are normally shared, unlike the single-zip CurseForge/Modrinth exports.

No API key needed: each mod's own .pw.toml embeds a direct download URL.

Needs Python 3.11+ (tomllib is built in). On older Python: pip install tomli
"""
import urllib.parse
import urllib.request
from pathlib import PurePosixPath

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # pip install tomli, for Python < 3.11

from packs import ResolvedFile, ResolvedPack

LOADER_KEYS = ("forge", "neoforge", "fabric", "quilt")


def _fetch_toml(url: str) -> dict:
    with urllib.request.urlopen(url) as resp:
        return tomllib.loads(resp.read().decode("utf-8"))


def parse_packwiz(pack_toml_url: str) -> ResolvedPack:
    """pack_toml_url: the full URL to pack.toml itself, e.g.
    'https://raw.githubusercontent.com/someuser/somepack/main/pack.toml'"""
    pack = _fetch_toml(pack_toml_url)
    base_url = pack_toml_url.rsplit("/", 1)[0] + "/"

    versions = pack.get("versions", {})
    loader, loader_version = None, None
    for key in LOADER_KEYS:
        if key in versions:
            loader, loader_version = key, versions[key]
            break

    index_filename = pack.get("index", {}).get("file", "index.toml")
    index = _fetch_toml(urllib.parse.urljoin(base_url, index_filename))

    files = []
    for entry in index.get("files", []):
        ref = entry["file"]  # e.g. "mods/sodium.pw.toml", or a direct file's own path

        if entry.get("metafile"):
            mod_meta = _fetch_toml(urllib.parse.urljoin(base_url, ref))
            if mod_meta.get("side") == "server":
                continue  # server-only, nothing the client needs

            download = mod_meta["download"]
            hash_format = download.get("hash-format")
            sha1 = download["hash"] if hash_format == "sha1" else None
            sha256 = download["hash"] if hash_format == "sha256" else None
            # murmur2 (CurseForge-sourced mods) isn't verified here — no cheap
            # stdlib implementation. That only skips the integrity check,
            # the download itself still happens fine.

            mod_dir = str(PurePosixPath(ref).parent)
            dest_path = mod_meta["filename"] if mod_dir in (".", "") \
                else f"{mod_dir}/{mod_meta['filename']}"

            files.append(ResolvedFile(path=dest_path, url=download["url"],
                                       sha1=sha1, sha256=sha256))
        else:
            # a directly-included file (configs, etc.) — hosted at the same
            # relative path as its entry in index.toml
            files.append(ResolvedFile(path=ref, url=urllib.parse.urljoin(base_url, ref)))

    return ResolvedPack(
        name=pack.get("name", "Packwiz Pack"),
        minecraft_version=versions.get("minecraft"),
        loader=loader,
        loader_version=loader_version,
        files=files,
    )


if __name__ == "__main__":
    import sys
    from pathlib import Path
    from packs import install_pack
    if len(sys.argv) < 3:
        print("usage: py packwiz.py <pack.toml URL> <instance_dir>")
        sys.exit(1)
    resolved = parse_packwiz(sys.argv[1])
    install_pack(resolved, Path(sys.argv[2]))
