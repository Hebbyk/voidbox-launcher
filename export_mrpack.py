"""
mc_launcher.export_mrpack — exports an already-installed instance into a
Modrinth .mrpack file (a zip containing modrinth.index.json + overrides/).

Same manifest-driven approach as export_packwiz.py: pack_manifest.json
(from packs.py / backfill_manifest.py) supplies the original download URL
for anything that has one; that becomes a `files[]` entry pointing at the
external URL, fetched fresh by whatever installs the .mrpack later.
Anything without a known URL (overrides, or files backfill's fingerprinting
couldn't identify) gets embedded directly under overrides/ inside the zip
instead — .mrpack supports this natively, no external host needed, unlike
packwiz's index.toml which only ever stores hashes, never bytes.

mrpack's hashes.sha1 and hashes.sha512 are both MANDATORY per Modrinth's own
spec (support.modrinth.com/en/articles/8802351-modrinth-modpack-format-mrpack,
checked before writing this) — neither is reliably available from what we
recorded at import time (CurseForge only ever gives sha1; our own manifest
never stores sha512 at all), so both are computed fresh from the actual
file on disk at export time instead of trusting stored hashes. That also
means the exported pack always matches what's really in minecraft/, even
if a file changed locally since import.

Same exclusions as export_packwiz.py (imported from there, not duplicated):
saves/screenshots/logs/crash-reports/downloads/data, usercache.json,
servers.dat, and any dot-dir.
"""
import hashlib
import json
import zipfile
from pathlib import Path

import export_packwiz  # shares DEFAULT_EXCLUDE_DIRS / DEFAULT_EXCLUDE_FILES
import modrinth  # shares LOADER_DEPENDENCY_KEYS (inverted below)

FORMAT_VERSION = 1
LOADER_TO_DEPENDENCY_KEY = {v: k for k, v in modrinth.LOADER_DEPENDENCY_KEYS.items()}


class MrpackExportError(Exception):
    pass


def _sha1_sha512(data: bytes) -> tuple[str, str]:
    return hashlib.sha1(data).hexdigest(), hashlib.sha512(data).hexdigest()


def export_to_mrpack(instance_root: Path, output_path: Path, pack_name: str | None = None,
                      version_id: str = "1.0.0", summary: str | None = None,
                      exclude_dirs: set[str] | None = None,
                      exclude_files: set[str] | None = None,
                      fallback_meta: dict | None = None, on_progress=None) -> Path:
    """Reads <instance_root>/pack_manifest.json + walks <instance_root>/minecraft/,
    writes a .mrpack file to output_path. Returns output_path.
    fallback_meta: the instance's own name/minecraft_version/loader/loader_version,
    used when it has no manifest. on_progress(done, total): optional, called per file."""
    instance_root = Path(instance_root).resolve()
    output_path = Path(output_path).resolve()
    mc_dir = instance_root / "minecraft"
    if not mc_dir.exists():
        raise MrpackExportError(f"No minecraft/ folder under {instance_root} — nothing to export")

    manifest = export_packwiz.load_manifest(instance_root, fallback_meta)
    if not manifest:
        raise MrpackExportError(
            f"No pack_manifest.json under {instance_root} — this instance wasn't "
            f"created from an imported pack (or predates manifest tracking)."
        )

    exclude_dirs = export_packwiz.DEFAULT_EXCLUDE_DIRS if exclude_dirs is None else exclude_dirs
    exclude_files = export_packwiz.DEFAULT_EXCLUDE_FILES if exclude_files is None else exclude_files
    manifest_by_path = {f["path"]: f for f in manifest["files"]}

    index_files = []
    skipped = []
    output_path.parent.mkdir(parents=True, exist_ok=True)

    referenced = [(rp, e) for rp, e in sorted(manifest_by_path.items()) if e.get("url")]
    overrides = export_packwiz.collect_override_files(mc_dir, manifest_by_path, exclude_dirs, exclude_files,
                                                      lambda e: bool(e.get("url")))
    total, done = len(referenced) + len(overrides), 0

    def tick():
        nonlocal done
        done += 1
        if on_progress:
            on_progress(done, total)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Files with a known external URL: referenced, not embedded.
        for rel_path, entry in referenced:  # (entries with no recoverable URL are embedded below instead)
            src = mc_dir / rel_path
            if not src.exists():
                skipped.append((rel_path, "listed in manifest but missing on disk"))
                tick()
                continue
            data = src.read_bytes()
            sha1, sha512 = _sha1_sha512(data)
            index_files.append({
                "path": rel_path.replace("\\", "/"),
                "hashes": {"sha1": sha1, "sha512": sha512},
                "downloads": [entry["url"]],
                "fileSize": len(data),
            })
            tick()

        # Everything else on disk: embedded directly under overrides/.
        for path, rel_str in overrides:
            zf.write(path, arcname="overrides/" + rel_str.replace("\\", "/"))
            tick()

        dependencies = {"minecraft": manifest["minecraft_version"]}
        loader = manifest.get("loader")
        if loader and loader != "vanilla":
            dep_key = LOADER_TO_DEPENDENCY_KEY.get(loader)
            if not dep_key:
                raise MrpackExportError(f"Don't know the mrpack dependency key for loader '{loader}'")
            dependencies[dep_key] = manifest["loader_version"]

        index = {
            "formatVersion": FORMAT_VERSION,
            "game": "minecraft",
            "versionId": version_id,
            "name": pack_name or manifest["name"],
            "files": index_files,
            "dependencies": dependencies,
        }
        if summary:
            index["summary"] = summary

        zf.writestr("modrinth.index.json", json.dumps(index, indent=2))

    if skipped:
        print(f"[export_mrpack] {len(skipped)} manifest file(s) skipped (missing on disk):")
        for rel_path, reason in skipped:
            print(f"    {rel_path}: {reason}")
    print(f"[export_mrpack] wrote {output_path}")
    return output_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: py export_mrpack.py <instance_dir> <output.mrpack> [pack_name]")
        sys.exit(1)
    pack_name = sys.argv[3] if len(sys.argv) > 3 else None
    export_to_mrpack(Path(sys.argv[1]), Path(sys.argv[2]), pack_name=pack_name)
