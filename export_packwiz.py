"""
mc_launcher.export_packwiz — exports an already-installed instance into a
standalone packwiz pack (pack.toml + index.toml + mods/*.pw.toml), written
to a local output directory ready to git-push / `packwiz serve` / zip up.

Source of truth is <instance_root>/pack_manifest.json, written by
packs.install_pack() at import time — it's the only place the original
external download URL + hash for each mod survive past the initial install
(the copy sitting in minecraft/mods/ has neither, so this can't be rebuilt
from the instance folder alone). Any file NOT covered by the manifest
(overrides that were copied in wholesale — configs, resourcepacks, etc.)
gets embedded directly instead, since there's no external URL to point a
metafile at — matches how real packwiz packs mix metafiles with plain
bundled files.

Needs Python 3.11+ (tomllib, stdlib only) — same requirement as packwiz.py.
No API calls, no network — this only reads what's already on disk.
"""
import hashlib
from pathlib import Path

from packs import read_manifest

PACK_FORMAT = "packwiz:1.1.0"

# Top-level folders under minecraft/ that are instance state, not pack
# content — never exported even if present. Override with `exclude_dirs=`.
# downloads/ is Minecraft's resource-pack download log; data/ is Fabric's
# local toggle-state for built-in resource packs — both purely local.
DEFAULT_EXCLUDE_DIRS = {"saves", "screenshots", "logs", "crash-reports", "downloads", "data"}

# Root-level files that are local session/account state, not pack content.
# usercache.json/servers.dat can leak your own or others' UUIDs, usernames,
# or server IPs if a pack built from this export gets shared.
DEFAULT_EXCLUDE_FILES = {"usercache.json", "servers.dat"}


class ExportError(Exception):
    pass


def load_manifest(instance_root: Path, fallback_meta: dict | None = None) -> dict | None:
    """The instance's pack_manifest.json if it has one. Otherwise — a blank
    instance nobody has added a mod to through the launcher — build an empty
    one from the instance's own metadata (name / minecraft_version / loader /
    loader_version, passed in by the caller). With an empty file list,
    everything on disk is simply embedded as overrides, which is exactly
    what exporting an instance with no tracked downloads should do.
    None (caller raises its usual error) if there's neither."""
    manifest = read_manifest(instance_root)
    if manifest:
        return manifest
    if fallback_meta and fallback_meta.get("name") and fallback_meta.get("minecraft_version"):
        return {"name": fallback_meta["name"], "minecraft_version": fallback_meta["minecraft_version"],
                "loader": fallback_meta.get("loader"), "loader_version": fallback_meta.get("loader_version"),
                "files": []}
    return None


def collect_override_files(mc_dir: Path, manifest_by_path: dict, exclude_dirs, exclude_files,
                            is_handled) -> list:
    """(path, relative-path-string) for every file that gets embedded directly:
    everything under minecraft/ except excluded state, dot-dirs, and files the
    manifest already covers (is_handled(entry) says whether it does)."""
    found = []
    for path in sorted(mc_dir.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(mc_dir)
        rel_str = str(rel)
        if rel.parts[0] in exclude_dirs or rel_str in exclude_files \
                or any(p.startswith(".") for p in rel.parts):
            continue
        entry = manifest_by_path.get(rel_str)
        if entry and is_handled(entry):
            continue
        found.append((path, rel_str))
    return found


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _toml_str(s: str) -> str:
    """Minimal TOML basic-string escaping — good enough for names/URLs/paths,
    which never contain control characters in practice."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mod_metafile_toml(name: str, filename: str, url: str, hash_format: str, hash_: str) -> str:
    return (
        f"name = {_toml_str(name)}\n"
        f"filename = {_toml_str(filename)}\n"
        f'side = "both"\n\n'
        f"[download]\n"
        f"url = {_toml_str(url)}\n"
        f'hash-format = "{hash_format}"\n'
        f"hash = {_toml_str(hash_)}\n"
    )


def export_to_packwiz(instance_root: Path, output_dir: Path, pack_name: str | None = None,
                       author: str | None = None, version: str = "1.0.0",
                       exclude_dirs: set[str] | None = None,
                       exclude_files: set[str] | None = None,
                       fallback_meta: dict | None = None, on_progress=None) -> Path:
    """Reads <instance_root>/pack_manifest.json + walks <instance_root>/minecraft/,
    writes a standalone packwiz pack into output_dir. Returns the path to pack.toml.
    fallback_meta: the instance's own name/minecraft_version/loader/loader_version,
    used when it has no manifest. on_progress(done, total): optional, called per file."""
    instance_root = Path(instance_root).resolve()
    output_dir = Path(output_dir).resolve()
    mc_dir = instance_root / "minecraft"
    if not mc_dir.exists():
        raise ExportError(f"No minecraft/ folder under {instance_root} — nothing to export")

    manifest = load_manifest(instance_root, fallback_meta)
    if not manifest:
        raise ExportError(
            f"No pack_manifest.json under {instance_root} — this instance wasn't "
            f"created from an imported pack (or predates manifest tracking), so "
            f"there's no record of which files came from where to export."
        )

    exclude_dirs = DEFAULT_EXCLUDE_DIRS if exclude_dirs is None else exclude_dirs
    exclude_files = DEFAULT_EXCLUDE_FILES if exclude_files is None else exclude_files
    manifest_by_path = {f["path"]: f for f in manifest["files"]}

    index_lines = ['hash-format = "sha256"\n']
    skipped = []

    referenced = [(rp, e) for rp, e in sorted(manifest_by_path.items()) if e.get("url")]
    overrides = collect_override_files(mc_dir, manifest_by_path, exclude_dirs, exclude_files,
                                        lambda e: bool(e.get("url")))
    total, done = len(referenced) + len(overrides), 0

    def tick():
        nonlocal done
        done += 1
        if on_progress:
            on_progress(done, total)

    # Manifest-known files: proper metafiles pointing at the original URL.
    for rel_path, entry in referenced:  # (entries with no recoverable URL are embedded below instead)
        src = mc_dir / rel_path
        if not src.exists():
            skipped.append((rel_path, "listed in manifest but missing on disk"))
            tick()
            continue

        if entry.get("sha256"):
            hash_format, hash_ = "sha256", entry["sha256"]
        elif entry.get("sha1"):
            hash_format, hash_ = "sha1", entry["sha1"]
        else:
            hash_format, hash_ = "sha256", _sha256(src.read_bytes())

        meta_rel = str(Path(rel_path).with_suffix(".pw.toml"))
        meta_name = Path(rel_path).stem
        meta_text = _mod_metafile_toml(meta_name, Path(rel_path).name, entry["url"],
                                        hash_format, hash_)
        _write(output_dir / meta_rel, meta_text)

        index_lines.append(
            f"\n[[files]]\n"
            f"file = {_toml_str(meta_rel)}\n"
            f"hash = {_toml_str(_sha256(meta_text.encode()))}\n"
            f"metafile = true\n"
        )
        tick()

    # Everything else on disk: embedded directly (no external URL to point to).
    for path, rel_str in overrides:
        data = path.read_bytes()
        dest = output_dir / rel_str
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        index_lines.append(
            f"\n[[files]]\nfile = {_toml_str(rel_str)}\nhash = {_toml_str(_sha256(data))}\n"
        )
        tick()

    index_text = "".join(index_lines)
    _write(output_dir / "index.toml", index_text)

    versions_lines = [f'minecraft = {_toml_str(manifest["minecraft_version"])}']
    loader = manifest.get("loader")
    if loader and loader != "vanilla":
        versions_lines.append(f'{loader} = {_toml_str(manifest["loader_version"])}')

    pack_lines = [f"name = {_toml_str(pack_name or manifest['name'])}"]
    if author:
        pack_lines.append(f"author = {_toml_str(author)}")
    pack_lines += [
        f"version = {_toml_str(version)}",
        f'pack-format = "{PACK_FORMAT}"',
        "",
        "[index]",
        'file = "index.toml"',
        'hash-format = "sha256"',
        f"hash = {_toml_str(_sha256(index_text.encode()))}",
        "",
        "[versions]",
        *versions_lines,
        "",
    ]
    pack_toml_path = output_dir / "pack.toml"
    _write(pack_toml_path, "\n".join(pack_lines))

    if skipped:
        print(f"[export_packwiz] {len(skipped)} manifest file(s) skipped (missing on disk):")
        for rel_path, reason in skipped:
            print(f"    {rel_path}: {reason}")
    print(f"[export_packwiz] wrote pack to {output_dir}")
    return pack_toml_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: py export_packwiz.py <instance_dir> <output_dir> [pack_name] [author]")
        sys.exit(1)
    pack_name = sys.argv[3] if len(sys.argv) > 3 else None
    author = sys.argv[4] if len(sys.argv) > 4 else None
    export_to_packwiz(Path(sys.argv[1]), Path(sys.argv[2]), pack_name=pack_name, author=author)
