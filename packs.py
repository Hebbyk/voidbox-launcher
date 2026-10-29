"""
mc_launcher.packs — shared shape + installer for imported modpacks.

CurseForge, Modrinth, and packwiz importers all parse their own format into
this same ResolvedPack shape, so there's exactly one download/install path
regardless of where the pack came from.

Note: this only gets the pack's actual content (mods, configs, resource
packs) in place. It does NOT install the mod loader itself (Forge/Fabric/
NeoForge/Quilt) — that's loaders.py, a separate step, since a resolved pack
just tells you which loader+version it needs.

After a successful install, the resolved file list (URLs + hashes) is saved to
<instance_root>/pack_manifest.json. That's what export reads later — without it
the URLs/hashes resolved at import time are thrown away. Lives next to the
instance's minecraft/ folder, not inside it, so it never ends up in an export
or gets clobbered by overrides.
"""
import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

import core  # reuses the size-checked downloader from the launch engine

MANIFEST_NAME = "pack_manifest.json"


@dataclass
class ResolvedFile:
    path: str  # relative to the instance's minecraft/ folder, e.g. "mods/sodium.jar"
    url: str
    sha1: str | None = None
    sha256: str | None = None
    size: int | None = None
    # Only ever known for files that came from (or were fingerprint-matched
    # against) CurseForge — export_curseforge.py needs the ID pair itself,
    # since CurseForge's manifest.json addresses files by {projectID,
    # fileID}, not URL. None for anything Modrinth/packwiz-sourced.
    curseforge_project_id: int | None = None
    curseforge_file_id: int | None = None


@dataclass
class ResolvedPack:
    name: str
    minecraft_version: str
    loader: str | None          # "forge" / "fabric" / "neoforge" / "quilt" / None (vanilla)
    loader_version: str | None
    files: list[ResolvedFile] = field(default_factory=list)
    overrides_dir: Path | None = None  # local folder to copy wholesale (configs, etc.)


def write_manifest(resolved: ResolvedPack, instance_root: Path) -> Path:
    """Saves what was resolved at import time. Only called after every download
    succeeded, so the manifest never lists a file that isn't actually there."""
    instance_root = Path(instance_root).resolve()
    instance_root.mkdir(parents=True, exist_ok=True)
    data = {
        "name": resolved.name,
        "minecraft_version": resolved.minecraft_version,
        "loader": resolved.loader,
        "loader_version": resolved.loader_version,
        "files": [asdict(f) for f in resolved.files],
    }
    path = instance_root / MANIFEST_NAME
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_manifest(instance_root: Path) -> dict | None:
    """None if this instance has no manifest (created before this existed, or
    a vanilla/loader-only instance that never went through install_pack)."""
    path = Path(instance_root) / MANIFEST_NAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def add_file_to_manifest(instance_root: Path, resolved_file: "ResolvedFile", *,
                          name: str, minecraft_version: str, loader: str | None,
                          loader_version: str | None) -> None:
    """Adds (or replaces, if the same path is already listed) one file's
    record in pack_manifest.json. Blank instances never go through
    install_pack and so start with no manifest at all — in that case one
    is created fresh here, using the name/version/loader the caller reads
    off the instance's own registry entry (not guessed)."""
    manifest = read_manifest(instance_root)
    if manifest is None:
        manifest = {"name": name, "minecraft_version": minecraft_version,
                     "loader": loader, "loader_version": loader_version, "files": []}
    norm = resolved_file.path.replace("\\", "/")
    kept = [f for f in manifest["files"] if f["path"].replace("\\", "/") != norm]
    kept.append(asdict(resolved_file))
    manifest["files"] = kept
    (Path(instance_root) / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2),
                                                      encoding="utf-8")


def remove_file_from_manifest(instance_root: Path, rel_path: str) -> bool:
    """Drops one file's record from pack_manifest.json. Returns True if an
    entry was actually removed. Paths are compared with separators
    normalized — backfill on Windows records 'mods\\\\x.jar' while importers
    record 'mods/x.jar', and both must match the same file."""
    manifest = read_manifest(instance_root)
    if not manifest:
        return False
    norm = rel_path.replace("\\", "/")
    kept = [f for f in manifest["files"] if f["path"].replace("\\", "/") != norm]
    if len(kept) == len(manifest["files"]):
        return False
    manifest["files"] = kept
    (Path(instance_root) / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2),
                                                      encoding="utf-8")
    return True


def install_pack(resolved: ResolvedPack, instance_root: Path, on_progress=None) -> None:
    """Downloads every resolved file into place and copies overrides in.
    on_progress, if given, is called as on_progress(current, total) after
    each file finishes — lets a caller (the GUI) show real progress instead
    of a generic spinner. Optional and CLI-safe: every existing caller that
    doesn't pass it keeps working exactly as before."""
    mc_dir = Path(instance_root).resolve() / "minecraft"

    total = len(resolved.files)
    for i, f in enumerate(resolved.files, 1):
        dest = mc_dir / f.path
        print(f"[packs] ({i}/{total}) {f.path}")
        core.download_file(f.url, dest, f.sha1, f.size, f.sha256)
        if on_progress:
            on_progress(i, total)

    if resolved.overrides_dir and Path(resolved.overrides_dir).exists():
        print("[packs] copying overrides...")
        shutil.copytree(resolved.overrides_dir, mc_dir, dirs_exist_ok=True)

    write_manifest(resolved, instance_root)

    print(f"[packs] '{resolved.name}' content installed — needs "
          f"{resolved.loader or 'vanilla'} {resolved.loader_version or ''} "
          f"on Minecraft {resolved.minecraft_version} (loader install is next, "
          f"not done by this step).")
