"""
mc_launcher.instances — tracks every instance you've created: its name, MC
version, which loader (if any), and where its files live. This is what lets
the app show a list of "your stuff" and have one Play button that works
regardless of whether an instance is vanilla, Fabric, Quilt, Forge, or
NeoForge — the actual loader install/merge still happens lazily at launch
time via loaders.py/forge.py, same as every CLI test this whole project has
used; this module just remembers WHICH one to call and WHERE to launch it.

Stored as a simple JSON file at %LOCALAPPDATA%\\MCLauncher\\instances.json
(a sibling of the shared game-file cache, since this is launcher metadata,
not shared game data).
"""
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import core

REGISTRY_FILENAME = "instances.json"


class InstanceError(Exception):
    pass


@dataclass
class Instance:
    name: str
    path: str  # instance root directory (str, not Path, so it's JSON-serializable)
    minecraft_version: str
    loader: str = "vanilla"  # "vanilla" | "fabric" | "quilt" | "forge" | "neoforge"
    loader_version: str = "latest"  # meaning depends on loader — see loaders.py/forge.py
    pack_source: dict = field(default_factory=dict)  # e.g. {"type": "modrinth", ...} — for export later
    icon_path: str | None = None  # absolute path to a custom icon image, if one's been set


def _registry_path() -> Path:
    return core.get_shared_cache_dir().parent / REGISTRY_FILENAME


def load_all() -> dict[str, Instance]:
    path = _registry_path()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {name: Instance(**data) for name, data in raw.items()}


def _save_all(registry: dict[str, Instance]):
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({name: asdict(inst) for name, inst in registry.items()}, indent=2),
                     encoding="utf-8")


def list_instances() -> list[Instance]:
    return list(load_all().values())


def get(name: str) -> Instance | None:
    return load_all().get(name)


def save(instance: Instance):
    registry = load_all()
    registry[instance.name] = instance
    _save_all(registry)


def remove(name: str, delete_files: bool = False) -> list[str]:
    """Removes the instance from the registry, and optionally deletes its
    files. Returns any paths that failed to delete (e.g. because Minecraft/
    Java is still running and holding a lock) instead of silently
    discarding them the way ignore_errors=True used to — the registry
    entry is removed either way, but leftover files are now reported
    rather than left as a silent orphan on disk."""
    registry = load_all()
    inst = registry.pop(name, None)
    _save_all(registry)
    failures: list[str] = []
    if inst and delete_files and Path(inst.path).exists():
        import shutil

        def _on_exc(function, path, exc):
            # A directory failing to rmdir is always just a downstream
            # consequence of a file inside it failing to unlink — reporting
            # both would show 3-4 "failed" paths for one real problem.
            if function is os.unlink:
                failures.append(path)

        shutil.rmtree(inst.path, onexc=_on_exc)
    return failures


# ---------------------------------------------------------------------------
# Editing existing instances
# ---------------------------------------------------------------------------

def rename(old_name: str, new_name: str) -> Instance:
    """Renames the registry entry only — inst.path (where the files actually
    live) is a separate field and is deliberately left alone, so nothing on
    disk moves and nothing that's holding files open can break the rename."""
    new_name = new_name.strip()
    if not new_name:
        raise InstanceError("Name can't be empty")
    registry = load_all()
    inst = registry.get(old_name)
    if not inst:
        raise InstanceError(f"No instance named '{old_name}'")
    if new_name == old_name:
        return inst
    if any(n.lower() == new_name.lower() for n in registry if n != old_name):
        raise InstanceError(f"An instance named '{new_name}' already exists")
    del registry[old_name]
    inst.name = new_name
    registry[new_name] = inst
    _save_all(registry)
    return inst


def list_mods(name: str) -> list[str]:
    """Jar filenames actually present in the instance's mods/ folder —
    read from disk, not the manifest, so it also shows mods that were
    dropped in by hand."""
    inst = get(name)
    if not inst:
        raise InstanceError(f"No instance named '{name}'")
    mods_dir = Path(inst.path) / "minecraft" / "mods"
    if not mods_dir.is_dir():
        return []
    return sorted((f.name for f in mods_dir.iterdir() if f.is_file() and f.suffix == ".jar"),
                  key=str.lower)


def remove_mod(name: str, filename: str) -> None:
    """Deletes one jar from the instance's mods/ folder and drops its
    record from pack_manifest.json (if it has one), so a later export
    doesn't reference a file that's gone. Raises if the file can't be
    deleted (e.g. still in use) rather than pretending it worked."""
    inst = get(name)
    if not inst:
        raise InstanceError(f"No instance named '{name}'")
    if Path(filename).name != filename:
        raise InstanceError(f"Invalid mod filename: {filename}")
    target = Path(inst.path) / "minecraft" / "mods" / filename
    if not target.is_file():
        raise InstanceError(f"'{filename}' isn't in {name}'s mods folder")
    target.unlink()
    import packs
    packs.remove_file_from_manifest(inst.path, f"mods/{filename}")


def set_icon(name: str, source_image_path: str) -> Instance:
    """Copies the chosen image into <instance_root>/icon<ext> — deliberately
    a sibling of minecraft/, not inside it, so export_*.py's file walk
    (which only ever looks under minecraft/) never picks it up. Any
    previous icon.* file is removed first so changing the icon a few
    times doesn't leave old copies lying around."""
    import shutil
    registry = load_all()
    inst = registry.get(name)
    if not inst:
        raise InstanceError(f"No instance named '{name}'")
    src = Path(source_image_path)
    if not src.is_file():
        raise InstanceError(f"'{source_image_path}' isn't a file")

    inst_root = Path(inst.path)
    for old in inst_root.glob("icon.*"):
        old.unlink(missing_ok=True)

    dest = inst_root / f"icon{src.suffix.lower()}"
    inst_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)

    inst.icon_path = str(dest)
    registry[name] = inst
    _save_all(registry)
    return inst


def open_folder(path: str) -> None:
    """Opens a folder in the OS file manager."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# ---------------------------------------------------------------------------
# Creating instances
# ---------------------------------------------------------------------------

def create_vanilla(name: str, minecraft_version: str, base_dir: Path) -> Instance:
    inst = Instance(name=name, path=str(Path(base_dir) / name),
                     minecraft_version=minecraft_version, loader="vanilla")
    save(inst)
    return inst


def create_modded(name: str, minecraft_version: str, loader: str, loader_version: str,
                   base_dir: Path) -> Instance:
    inst = Instance(name=name, path=str(Path(base_dir) / name),
                     minecraft_version=minecraft_version, loader=loader,
                     loader_version=loader_version)
    save(inst)
    return inst


def detect_pack_format(pack_path) -> str:
    """Peeks inside the archive instead of trusting the extension — both
    CurseForge zips and Modrinth .mrpacks are just zip files, and a .mrpack
    that's been renamed to .zip (or vice versa) is still perfectly valid
    once opened. Extension-only dispatch fails that case with a confusing
    "no item named 'manifest.json'" KeyError instead of actually looking.
    Returns "modrinth", "curseforge", or "unknown"."""
    try:
        with zipfile.ZipFile(pack_path) as zf:
            names = set(zf.namelist())
    except (zipfile.BadZipFile, OSError):
        return "unknown"
    if "modrinth.index.json" in names:
        return "modrinth"
    if "manifest.json" in names:
        return "curseforge"
    return "unknown"


def create_from_pack_file(name: str, pack_path: str, base_dir: Path,
                           curseforge_api_key: str | None = None, on_progress=None) -> Instance:
    """Auto-detects the pack format by looking inside the archive (see
    detect_pack_format), downloads its mods into a new instance, and
    registers it. on_progress(current, total), if given, is forwarded to
    packs.install_pack for real download progress."""
    import packs
    instance_root = Path(base_dir) / name

    fmt = detect_pack_format(pack_path)
    if fmt == "modrinth":
        import modrinth
        resolved = modrinth.parse_mrpack(pack_path)
        source = {"type": "modrinth"}
    elif fmt == "curseforge":
        if not curseforge_api_key:
            raise InstanceError("This looks like a CurseForge pack — needs an API key")
        import curseforge
        resolved = curseforge.parse_curseforge_zip(pack_path, curseforge_api_key)
        source = {"type": "curseforge"}
    else:
        raise InstanceError(
            f"Don't recognize this as a pack file (found neither modrinth.index.json "
            f"nor manifest.json inside): {pack_path}")

    packs.install_pack(resolved, instance_root, on_progress=on_progress)

    inst = Instance(
        name=name, path=str(instance_root), minecraft_version=resolved.minecraft_version,
        loader=resolved.loader or "vanilla", loader_version=resolved.loader_version or "latest",
        pack_source=source,
    )
    save(inst)
    return inst


def create_from_packwiz_url(name: str, pack_toml_url: str, base_dir: Path, on_progress=None) -> Instance:
    import packs
    import packwiz
    resolved = packwiz.parse_packwiz(pack_toml_url)
    instance_root = Path(base_dir) / name
    packs.install_pack(resolved, instance_root, on_progress=on_progress)

    inst = Instance(
        name=name, path=str(instance_root), minecraft_version=resolved.minecraft_version,
        loader=resolved.loader or "vanilla", loader_version=resolved.loader_version or "latest",
        pack_source={"type": "packwiz", "url": pack_toml_url},
    )
    save(inst)
    return inst


# ---------------------------------------------------------------------------
# Launching — the one function the GUI actually calls
# ---------------------------------------------------------------------------

def launch(name: str, auth: dict, java_path: str | None = None, memory_mb: int = 4096,
           extra_jvm_args: list[str] | None = None):
    inst = get(name)
    if not inst:
        raise InstanceError(f"No instance named '{name}'")

    if inst.loader == "vanilla":
        core.prepare_and_launch(inst.path, inst.minecraft_version, auth,
                                 memory_mb=memory_mb, java_path=java_path,
                                 extra_jvm_args=extra_jvm_args)
    elif inst.loader in ("fabric", "quilt"):
        import loaders
        installer = loaders.install_fabric if inst.loader == "fabric" else loaders.install_quilt
        version_info = installer(inst.minecraft_version, inst.loader_version)
        core.prepare_and_launch(inst.path, version_info["id"], auth, memory_mb=memory_mb,
                                 version_info=version_info, java_path=java_path,
                                 extra_jvm_args=extra_jvm_args)
    elif inst.loader in ("forge", "neoforge"):
        import forge
        forge.install_and_launch(inst.path, inst.minecraft_version, auth, kind=inst.loader,
                                  choice=inst.loader_version, java_path=java_path,
                                  memory_mb=memory_mb)
    else:
        raise InstanceError(f"Unknown loader type: {inst.loader}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: py instances.py list")
        print("       py instances.py launch <name> <username>")
        print("       py instances.py delete <name> [--keep-files]")
        sys.exit(1)

    if sys.argv[1] == "list":
        insts = list_instances()
        if not insts:
            print("No instances yet.")
        for inst in insts:
            print(f"- {inst.name}: {inst.loader} {inst.loader_version} on "
                  f"Minecraft {inst.minecraft_version}  ({inst.path})")

    elif sys.argv[1] == "launch":
        name, username = sys.argv[2], sys.argv[3]
        launch(name, core.offline_auth(username))

    elif sys.argv[1] == "delete":
        if len(sys.argv) < 3:
            print("usage: py instances.py delete <name> [--keep-files]")
            sys.exit(1)
        name = sys.argv[2]
        keep_files = "--keep-files" in sys.argv[3:]
        inst = get(name)
        if not inst:
            print(f"No instance named '{name}'")
            sys.exit(1)
        verb = f"Remove '{name}' from the list only (files kept at {inst.path})" if keep_files \
            else f"Delete '{name}' AND all its files at {inst.path} (mods, saves, etc.)"
        confirm = input(f"{verb} — type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("Cancelled.")
            sys.exit(0)
        failures = remove(name, delete_files=not keep_files)
        if failures:
            print(f"Removed from the list, but {len(failures)} file(s) couldn't be deleted "
                  f"(probably still in use — close Minecraft/Java first if it's running):")
            for f in failures:
                print(f"  {f}")
        else:
            print(f"'{name}' deleted." if not keep_files
                  else f"'{name}' removed from the list (files kept).")
