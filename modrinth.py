"""
mc_launcher.modrinth — imports a .mrpack (Modrinth modpack export).

No API key needed: unlike CurseForge, a .mrpack embeds real, direct CDN
download URLs for every file already, so parsing it is all that's needed.
"""
import json
import tempfile
import zipfile
from pathlib import Path

from packs import ResolvedFile, ResolvedPack

LOADER_DEPENDENCY_KEYS = {
    "fabric-loader": "fabric",
    "forge": "forge",
    "neoforge": "neoforge",
    "quilt-loader": "quilt",
}


def parse_mrpack(mrpack_path: Path) -> ResolvedPack:
    mrpack_path = Path(mrpack_path)
    extract_dir = Path(tempfile.mkdtemp(prefix="mrpack_"))

    with zipfile.ZipFile(mrpack_path) as zf:
        zf.extractall(extract_dir)

    index = json.loads((extract_dir / "modrinth.index.json").read_text(encoding="utf-8"))
    deps = index.get("dependencies", {})

    loader, loader_version = None, None
    for key, name in LOADER_DEPENDENCY_KEYS.items():
        if key in deps:
            loader, loader_version = name, deps[key]
            break

    files = []
    for entry in index.get("files", []):
        env = entry.get("env")
        # Only install files required on the client — skip "optional" (user's
        # choice, not ours to make) and "unsupported". No env block = required.
        if env and env.get("client") != "required":
            continue
        files.append(ResolvedFile(
            path=entry["path"],
            url=entry["downloads"][0],
            sha1=entry.get("hashes", {}).get("sha1"),
            size=entry.get("fileSize"),
        ))

    overrides_dir = extract_dir / "overrides"
    server_overrides_dir = extract_dir / "server-overrides"
    # Client launcher: skip server-overrides entirely (per spec, that's a
    # server-side layer applied after overrides — not relevant here).
    del server_overrides_dir

    return ResolvedPack(
        name=index.get("name", mrpack_path.stem),
        minecraft_version=deps.get("minecraft"),
        loader=loader,
        loader_version=loader_version,
        files=files,
        overrides_dir=overrides_dir if overrides_dir.exists() else None,
    )


if __name__ == "__main__":
    import sys
    from packs import install_pack
    if len(sys.argv) < 3:
        print("usage: py modrinth.py <pack.mrpack> <instance_dir>")
        sys.exit(1)
    resolved = parse_mrpack(sys.argv[1])
    install_pack(resolved, Path(sys.argv[2]))
