"""
mc_launcher.export_curseforge — exports an already-installed instance into
a CurseForge modpack .zip (manifest.json + overrides/).

Fundamentally different from the packwiz/mrpack exporters: CurseForge's
manifest.json addresses each mod by {projectID, fileID} — it never stores a
download URL at all; the CurseForge App/launcher resolves those IDs back
into a URL via the API at install time (same as curseforge.py does on
import). That means export can only produce a real manifest.json entry for
a file where we actually know its CurseForge IDs:

- Mods originally imported FROM CurseForge — curseforge.py now records
  curseforge_project_id/curseforge_file_id on each ResolvedFile (previously
  discarded once the download URL was resolved).
- Mods backfill_manifest.py identified via CurseForge fingerprint matching
  — same two fields, recovered from the /fingerprints response.

Anything else — Modrinth/packwiz-sourced mods, unresolved files, and every
non-mod override (configs, resourcepacks) — has no CurseForge ID to point
at, so it's physically copied into overrides/ instead, exactly like a
real CurseForge pack's overrides folder: the CurseForge App and other
launchers copy that folder into the instance wholesale in addition to
resolving the manifest's file list, so a jar sitting in overrides/mods/
installs the same way a manifest-resolved one does.

Same exclusions as export_packwiz.py/export_mrpack.py (imported, not
duplicated): saves/screenshots/logs/crash-reports/downloads/data,
usercache.json, servers.dat, and any dot-dir.
"""
import json
import zipfile
from pathlib import Path

import export_packwiz  # shares DEFAULT_EXCLUDE_DIRS / DEFAULT_EXCLUDE_FILES

MANIFEST_TYPE = "minecraftModpack"
MANIFEST_VERSION = 1

# curseforge.py builds a loader's manifest "id" as "<loader>-<loader_version>"
# (e.g. "fabric-0.15.11") when parsing — mirrored here on the way back out.
LOADER_MANIFEST_PREFIX = {"forge": "forge", "fabric": "fabric",
                           "quilt": "quilt", "neoforge": "neoforge"}


class CurseForgeExportError(Exception):
    pass


def export_to_curseforge(instance_root: Path, output_path: Path, pack_name: str | None = None,
                          author: str | None = None, version: str = "1.0.0",
                          exclude_dirs: set[str] | None = None,
                          exclude_files: set[str] | None = None,
                          fallback_meta: dict | None = None, on_progress=None) -> Path:
    """Reads <instance_root>/pack_manifest.json + walks <instance_root>/minecraft/,
    writes a CurseForge pack .zip to output_path. Returns output_path.
    fallback_meta: the instance's own name/minecraft_version/loader/loader_version,
    used when it has no manifest. on_progress(done, total): optional, called per file."""
    instance_root = Path(instance_root).resolve()
    output_path = Path(output_path).resolve()
    mc_dir = instance_root / "minecraft"
    if not mc_dir.exists():
        raise CurseForgeExportError(f"No minecraft/ folder under {instance_root} — nothing to export")

    manifest = export_packwiz.load_manifest(instance_root, fallback_meta)
    if not manifest:
        raise CurseForgeExportError(
            f"No pack_manifest.json under {instance_root} — this instance wasn't "
            f"created from an imported pack (or predates manifest tracking)."
        )

    exclude_dirs = export_packwiz.DEFAULT_EXCLUDE_DIRS if exclude_dirs is None else exclude_dirs
    exclude_files = export_packwiz.DEFAULT_EXCLUDE_FILES if exclude_files is None else exclude_files
    manifest_by_path = {f["path"]: f for f in manifest["files"]}

    cf_entries = []
    no_cf_id = []
    output_path.parent.mkdir(parents=True, exist_ok=True)

    overrides = export_packwiz.collect_override_files(
        mc_dir, manifest_by_path, exclude_dirs, exclude_files,
        lambda e: bool(e.get("curseforge_project_id") and e.get("curseforge_file_id")))
    total, done = len(manifest_by_path) + len(overrides), 0

    def tick():
        nonlocal done
        done += 1
        if on_progress:
            on_progress(done, total)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Files with known CurseForge IDs: referenced by ID, not embedded.
        for rel_path, entry in sorted(manifest_by_path.items()):
            project_id = entry.get("curseforge_project_id")
            file_id = entry.get("curseforge_file_id")
            if not (project_id and file_id):
                no_cf_id.append(rel_path)
                tick()
                continue  # no known CurseForge ID — embedded under overrides/ below instead
            cf_entries.append({"projectID": project_id, "fileID": file_id, "required": True})
            tick()

        if no_cf_id:
            print(f"[export_curseforge] {len(no_cf_id)} manifest file(s) have no known "
                  f"CurseForge ID (not CurseForge-sourced, or backfill couldn't fingerprint-"
                  f"match them) — embedding directly under overrides/ instead: {no_cf_id}")

        # Everything else on disk: embedded directly under overrides/. This
        # covers every no-CF-ID manifest file above (by construction, since
        # they were never added to cf_entries) plus ordinary overrides.
        for path, rel_str in overrides:
            zf.write(path, arcname="overrides/" + rel_str.replace("\\", "/"))
            tick()

        loader = manifest.get("loader")
        mod_loaders = []
        if loader and loader != "vanilla":
            prefix = LOADER_MANIFEST_PREFIX.get(loader)
            if not prefix:
                raise CurseForgeExportError(f"Don't know the CurseForge loader id for '{loader}'")
            mod_loaders = [{"id": f"{prefix}-{manifest['loader_version']}", "primary": True}]

        cf_manifest = {
            "minecraft": {"version": manifest["minecraft_version"], "modLoaders": mod_loaders},
            "manifestType": MANIFEST_TYPE,
            "manifestVersion": MANIFEST_VERSION,
            "name": pack_name or manifest["name"],
            "version": version,
            "author": author or "",
            "files": cf_entries,
            "overrides": "overrides",
        }
        zf.writestr("manifest.json", json.dumps(cf_manifest, indent=2))

    print(f"[export_curseforge] wrote {output_path} ({len(cf_entries)} resolved by ID, "
          f"{len(no_cf_id)} embedded directly)")
    return output_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: py export_curseforge.py <instance_dir> <output.zip> [pack_name] [author]")
        sys.exit(1)
    pack_name = sys.argv[3] if len(sys.argv) > 3 else None
    author = sys.argv[4] if len(sys.argv) > 4 else None
    export_to_curseforge(Path(sys.argv[1]), Path(sys.argv[2]), pack_name=pack_name, author=author)
