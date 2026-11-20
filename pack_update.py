"""
pack_update.py - updates an installed modpack IN PLACE to another version of the same pack.

The mods folder ends up with EXACTLY the new pack's mods, so nothing leftover (old pack mods, mods added by hand,
mods from an older version) can break the instance. A mod that is already there with the right hash is kept and
not downloaded again; a pack mod you had turned off (.jar.disabled) stays off. Every other file in mods\\ is moved
into the rollback snapshot, so Undo brings it back.

Other pack files (resource packs, shaders, ...) are matched by the pack record, and override files (configs,
kubejs, ...) use a 3-way rule using hashes recorded at install/update time ("override_hashes"):
    not on disk                      -> added
    on disk, same as what the pack   -> replaced by the new pack's version (the player never edited it)
      installed last time
    on disk, edited by the player,   -> kept as the player has it (counted as a conflict)
      or no record (older instance)
Never touched: saves, options.txt, servers.dat, screenshots.

Everything replaced or removed is first saved under <instance>\\rollback_pack\\<time>\\ and undo() puts it back.
"""
import hashlib
import json
import shutil
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import atomicio
import core
import instances
import packs

SNAP_DIRNAME = "rollback_pack"
TMP_DIRNAME = ".pu_tmp"
SKIP_ON_DUPLICATE = {SNAP_DIRNAME, TMP_DIRNAME}


class PackUpdateError(Exception):
    pass


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _same(a: Path, b: Path) -> bool:
    return a.stat().st_size == b.stat().st_size and _sha1(a) == _sha1(b)


# ---------------------------------------------------------------------------
# Which pack is this instance, and which versions exist
# ---------------------------------------------------------------------------

def source_info(inst) -> dict | None:
    """{"type", "project_id", "version_id", ...} or None when the instance isn't linked to a pack project
    (imported from a file, or installed before 1.1.5 - see link())."""
    s = inst.pack_source or {}
    if s.get("type") in ("modrinth", "curseforge") and s.get("project_id"):
        return s
    return None


def link(inst_name: str, source_type: str, project_id, version_id=None, version_name=None):
    """Remembers which pack project (and version) an instance came from. Called after a fresh install, or when
    the player links an older instance to its pack by hand."""
    inst = instances.get(inst_name)
    if inst is None:
        raise PackUpdateError("That instance no longer exists")
    src = dict(inst.pack_source or {})
    if str(src.get("project_id", "")) != str(project_id) or src.get("type") != source_type:
        src.pop("version_id", None)        # a different pack page: the old version id means nothing there
        src.pop("version_name", None)
    src.update({"type": source_type, "project_id": project_id})
    if version_id is not None:
        src["version_id"] = version_id
    if version_name is not None:
        src["version_name"] = version_name
    inst.pack_source = src
    instances.save(inst)


def list_versions(inst, cf_api_key=None) -> list[dict]:
    """Versions of the linked pack, in the order the site returns them (newest first). Each dict is the one
    search.get_*_versions/get_curseforge_files returns, plus "installed": True on the one that is installed."""
    import search
    src = source_info(inst)
    if src is None:
        raise PackUpdateError("This instance isn't linked to a modpack page yet")
    if src["type"] == "modrinth":
        versions = search.get_modrinth_versions(src["project_id"])
    else:
        if not cf_api_key:
            raise PackUpdateError("Need a CurseForge API key to list this pack's files")
        versions = search.get_curseforge_files(src["project_id"], cf_api_key, limit=50)
    cur = str(src.get("version_id", ""))
    for v in versions:
        v["installed"] = bool(cur) and str(v["id"]) == cur
    return versions


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

@dataclass
class UpdatePlan:
    version: dict
    resolved: packs.ResolvedPack
    add: list = field(default_factory=list)        # ResolvedFile
    change: list = field(default_factory=list)     # ResolvedFile (same path, different content)
    remove: list = field(default_factory=list)     # relative paths
    unchanged: int = 0
    legacy_kept: list = field(default_factory=list)  # paths no longer in the pack, kept because the instance is older
    ov_add: list = field(default_factory=list)       # override relative paths
    ov_overwrite: list = field(default_factory=list)
    ov_conflict: list = field(default_factory=list)  # edited by the player, kept as they are
    ov_new_hashes: dict = field(default_factory=dict)
    ov_dir: Path | None = None
    mc_changed: bool = False
    loader_changed: bool = False
    warnings: list = field(default_factory=list)


def plan_update(inst, version: dict, cf_api_key=None, progress=None) -> UpdatePlan:
    """Downloads the chosen pack file and works out what would change. Nothing in the instance is touched."""
    import search
    say = progress or (lambda _t: None)
    inst = instances.get(inst.name) or inst
    root = Path(inst.path)
    manifest = packs.read_manifest(root)
    if manifest is None:
        raise PackUpdateError("This instance has no pack record (pack_manifest.json), so it can't be compared "
                              "with a new version. Install the new version as a separate instance instead.")

    tmp = root / TMP_DIRNAME
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    say("Downloading the new pack version...")
    pack_path = search.download_pack_file(version.get("url"), version["filename"], tmp)
    fmt = instances.detect_pack_format(pack_path)
    say("Reading it...")
    if fmt == "modrinth":
        import modrinth
        resolved = modrinth.parse_mrpack(pack_path)
    elif fmt == "curseforge":
        if not cf_api_key:
            raise PackUpdateError("This is a CurseForge pack - it needs a CurseForge API key")
        import curseforge
        resolved = curseforge.parse_curseforge_zip(str(pack_path), cf_api_key)
    else:
        shutil.rmtree(tmp, ignore_errors=True)
        raise PackUpdateError("The downloaded file isn't a modpack (no modrinth.index.json or manifest.json)")
    shutil.rmtree(tmp, ignore_errors=True)     # the pack file itself isn't needed again; apply_update re-creates the folder

    old = {_norm(f["path"]): f for f in manifest.get("files", [])}
    new = {_norm(f.path): f for f in resolved.files}
    pack_files = manifest.get("pack_files")
    legacy = pack_files is None
    old_pack = {_norm(p) for p in pack_files} if not legacy else set()
    mc_dir = root / "minecraft"

    plan = UpdatePlan(version=version, resolved=resolved, ov_dir=resolved.overrides_dir)

    say("Checking installed mods...")
    disk_mods: dict[str, Path] = {}          # every jar / .jar.disabled under mods\\, keyed by path relative to minecraft\\
    if (mc_dir / "mods").is_dir():
        for f in (mc_dir / "mods").rglob("*"):
            if f.is_file() and f.name.lower().endswith((".jar", ".jar.disabled")):
                disk_mods[_norm(str(f.relative_to(mc_dir)))] = f
    new_mods = set()
    for path, rf in new.items():
        rec = old.get(path)
        if path.startswith("mods/"):
            new_mods.add(path)
            cur = disk_mods.get(path) or disk_mods.get(path + ".disabled")
            if cur is not None and ((rf.sha1 and _sha1(cur) == rf.sha1)
                                    or (not rf.sha1 and rec and rf.url == rec.get("url"))):
                plan.unchanged += 1                              # right file already there (maybe turned off: stays off)
            elif cur is None:
                plan.add.append(rf)
            else:
                plan.change.append(rf)
                if cur.name.lower().endswith(".disabled"):
                    plan.remove.append(path + ".disabled")       # the new build comes in enabled
            continue
        on_disk = mc_dir / path                                    # other pack files: judged by the pack record
        if rec is None or not on_disk.exists():
            plan.add.append(rf)
        elif (rf.sha1 and rec.get("sha1") and rf.sha1 == rec["sha1"]) or (not rf.sha1 and rf.url == rec.get("url")):
            plan.unchanged += 1
        else:
            plan.change.append(rf)

    # every other mod file goes (pack leftovers, hand-added mods): the folder must match the new pack exactly
    for rel in disk_mods:
        base = rel[:-9] if rel.endswith(".disabled") else rel
        if base not in new_mods and rel not in plan.remove:
            plan.remove.append(rel)
    # non-mod files the pack dropped (resource packs, ...); older instances can't tell what was the pack's
    gone = [p for p in (old_pack if not legacy else old) if p not in new and not p.startswith("mods/")]
    if legacy:
        plan.legacy_kept = sorted(gone)
    else:
        plan.remove += sorted(gone)
    plan.remove.sort()

    # overrides (3-way)
    old_hashes = manifest.get("override_hashes") or {}
    if plan.ov_dir and Path(plan.ov_dir).is_dir():
        ovd = Path(plan.ov_dir)
        for f in sorted(p for p in ovd.rglob("*") if p.is_file()):
            rel = _norm(str(f.relative_to(ovd)))
            plan.ov_new_hashes[rel] = _sha1(f)
            dest = mc_dir / rel
            if not dest.exists():
                plan.ov_add.append(rel)
            elif _same(f, dest):
                continue                                     # identical already
            elif rel in old_hashes and _sha1(dest) == old_hashes[rel]:
                plan.ov_overwrite.append(rel)                # still exactly what the old pack installed
            else:
                plan.ov_conflict.append(rel)                 # player's edit (or unknown) -> keep

    plan.mc_changed = bool(resolved.minecraft_version) and resolved.minecraft_version != inst.minecraft_version
    plan.loader_changed = (resolved.loader or "vanilla") != inst.loader or (
        resolved.loader_version and resolved.loader_version != inst.loader_version
        and inst.loader_version != "latest")
    if plan.mc_changed:
        plan.warnings.append(f"Minecraft changes {inst.minecraft_version} -> {resolved.minecraft_version}.")
    if (resolved.loader or "vanilla") != inst.loader:
        plan.warnings.append(f"The pack switches loader: {inst.loader} -> {resolved.loader or 'vanilla'}.")
    return plan


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

@dataclass
class ApplyResult:
    added: int = 0
    changed: int = 0
    removed: int = 0
    ov_added: int = 0
    ov_overwritten: int = 0
    ov_kept: int = 0
    snapshot: Path | None = None
    worlds_backup: Path | None = None


def apply_update(inst, plan: UpdatePlan, backup_worlds: bool | None = None, progress=None,
                 on_file_progress=None, on_copy_progress=None) -> ApplyResult:
    """backup_worlds=None -> back the worlds up only when Minecraft's version changes.
    All downloads are finished and checked BEFORE anything in the instance is touched; if one fails (e.g. a mod
    author blocks downloads) the update stops with nothing changed."""
    say = progress or (lambda _t: None)
    inst = instances.get(inst.name)
    if inst is None:
        raise PackUpdateError("That instance no longer exists")
    root = Path(inst.path)
    mc_dir = root / "minecraft"
    tmp = root / TMP_DIRNAME
    tmp.mkdir(parents=True, exist_ok=True)
    result = ApplyResult()

    try:
        # 1) download + check
        todo = plan.add + plan.change
        failed = []
        dl: dict[str, Path] = {}
        for i, rf in enumerate(todo, 1):
            say(f"Downloading {i}/{len(todo)}: {Path(rf.path).name}")
            dest = tmp / "files" / _norm(rf.path)
            try:
                if not rf.url:
                    raise RuntimeError("the author blocks automatic downloads")
                core.download_file(rf.url, dest, rf.sha1, rf.size, rf.sha256)
                if rf.path.lower().endswith(".jar") and not zipfile.is_zipfile(dest):
                    raise RuntimeError("the download isn't a valid jar file")
                dl[_norm(rf.path)] = dest
            except (OSError, RuntimeError) as e:
                failed.append(f"{rf.path}: {e}")
            if on_file_progress:
                on_file_progress(i, len(todo))
        if failed:
            raise PackUpdateError("Nothing was changed. These files couldn't be downloaded:\n"
                                  + "\n".join(failed[:15]) + ("\n..." if len(failed) > 15 else ""))

        # 2) snapshot
        stamp, n = time.strftime("%Y%m%d-%H%M%S"), 2
        snap = root / SNAP_DIRNAME / stamp
        while snap.exists():
            snap = root / SNAP_DIRNAME / f"{stamp}-{n}"
            n += 1
        (snap / "files").mkdir(parents=True)
        result.snapshot = snap
        manifest = packs.read_manifest(root) or {}
        meta = {"kind": "pack_update", "time": int(time.time()), "undone": False,
                "from_mc": inst.minecraft_version, "from_loader": inst.loader,
                "from_loader_version": inst.loader_version, "from_pack_source": dict(inst.pack_source or {}),
                "to_version": plan.version.get("name"), "had_manifest": bool(manifest),
                "saved": [], "created": [], "worlds_backup": False}

        def save_meta():
            atomicio.write_text(snap / "meta.json", json.dumps(meta, indent=2))

        if manifest:
            atomicio.write_text(snap / packs.MANIFEST_NAME, json.dumps(manifest, indent=2))
        if backup_worlds is None:
            backup_worlds = plan.mc_changed
        if backup_worlds and (mc_dir / "saves").is_dir():
            say("Backing up worlds...")
            import version_change
            version_change.copy_tree(mc_dir / "saves", snap / "saves", on_copy_progress)
            result.worlds_backup, meta["worlds_backup"] = snap / "saves", True
        save_meta()

        def stash(rel: str, move: bool = False):
            """saves an existing file into the snapshot (moves it when move=True); returns True if there was one."""
            src = mc_dir / rel
            if not src.is_file():
                return False
            out = snap / "files" / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            if move:
                shutil.move(str(src), str(out))
            else:
                shutil.copy2(src, out)
            meta["saved"].append(rel)
            return True

        # 3) swap (meta is saved even if this throws halfway, so undo() can still put things back)
        say("Applying...")
        try:
            for rel in plan.remove:
                if stash(rel, move=True):
                    result.removed += 1
            for rf in plan.change:
                rel = _norm(rf.path)
                existed = stash(rel)
                (mc_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dl[rel]), str(mc_dir / rel))
                if not existed:                  # e.g. the old copy was turned off (.disabled): undo must remove this one
                    meta["created"].append(rel)
                result.changed += 1
            for rf in plan.add:
                rel = _norm(rf.path)
                existed = stash(rel)             # a same-named file the pack didn't know about
                (mc_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dl[rel]), str(mc_dir / rel))
                if not existed:
                    meta["created"].append(rel)
                result.added += 1
            if plan.ov_dir:
                ovd = Path(plan.ov_dir)
                for rel in plan.ov_add + plan.ov_overwrite:
                    existed = stash(rel)
                    dest = mc_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(ovd / rel, dest)
                    if not existed:
                        meta["created"].append(rel)
                result.ov_added, result.ov_overwritten = len(plan.ov_add), len(plan.ov_overwrite)
                result.ov_kept = len(plan.ov_conflict)

            # 4) the instance's settings + pack record
            res = plan.resolved
            inst.minecraft_version = res.minecraft_version or inst.minecraft_version
            inst.loader = res.loader or "vanilla"
            inst.loader_version = res.loader_version or "latest"
            src = dict(inst.pack_source or {})
            src["version_id"] = plan.version.get("id")
            src["version_name"] = plan.version.get("name")
            inst.pack_source = src
            instances.save(inst)

            new_paths = {_norm(f.path) for f in res.files}
            old_pack = {_norm(p) for p in manifest.get("pack_files") or []}
            gone = {r[:-9] if r.endswith(".disabled") else r for r in plan.remove}
            # records of mods the player added by hand (or legacy leftovers) stay; pack records are replaced
            keep = [f for f in manifest.get("files", [])
                    if _norm(f["path"]) not in new_paths and _norm(f["path"]) not in gone
                    and _norm(f["path"]) not in old_pack]
            hashes = dict(manifest.get("override_hashes") or {})
            for rel in plan.ov_add + plan.ov_overwrite:
                hashes[rel] = plan.ov_new_hashes[rel]
            for rel in plan.ov_conflict:
                hashes.pop(rel, None)               # the player owns it now
            new_manifest = {"name": res.name, "minecraft_version": inst.minecraft_version,
                            "loader": res.loader, "loader_version": res.loader_version,
                            "files": keep + [asdict(f) for f in res.files],
                            "pack_files": sorted(new_paths), "override_hashes": hashes}
            atomicio.write_text(root / packs.MANIFEST_NAME, json.dumps(new_manifest, indent=2))
        finally:
            save_meta()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return result


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------

def latest_snapshot(inst) -> Path | None:
    base = Path(inst.path) / SNAP_DIRNAME
    if not base.is_dir():
        return None
    for d in sorted((p for p in base.iterdir() if (p / "meta.json").is_file()), reverse=True):
        try:
            if not json.loads((d / "meta.json").read_text(encoding="utf-8")).get("undone"):
                return d
        except (OSError, ValueError):
            continue
    return None


def undo(inst):
    """Reverts the most recent pack update: files it created are removed, files it replaced/removed come back,
    the old pack record and Minecraft/loader settings are restored. Worlds are NOT rolled back (that would erase
    what you played since); a worlds backup, if one was made, stays where it is.
    Returns (restored count, problems, worlds backup path or None)."""
    inst = instances.get(inst.name) or inst
    snap = latest_snapshot(inst)
    if snap is None:
        return 0, [], None
    root = Path(inst.path)
    mc_dir = root / "minecraft"
    meta = json.loads((snap / "meta.json").read_text(encoding="utf-8"))
    problems, restored = [], 0
    for rel in meta.get("created", []):
        try:
            (mc_dir / rel).unlink(missing_ok=True)
        except OSError as e:
            problems.append(f"{rel}: {e}")
    for rel in meta.get("saved", []):
        src = snap / "files" / rel
        if not src.is_file():
            problems.append(f"{rel}: the saved copy is gone")
            continue
        try:
            (mc_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, mc_dir / rel)
            restored += 1
        except OSError as e:
            problems.append(f"{rel}: {e}")
    if meta.get("had_manifest") and (snap / packs.MANIFEST_NAME).is_file():
        shutil.copy2(snap / packs.MANIFEST_NAME, root / packs.MANIFEST_NAME)
    inst.minecraft_version = meta["from_mc"]
    inst.loader = meta["from_loader"]
    inst.loader_version = meta["from_loader_version"]
    inst.pack_source = meta.get("from_pack_source") or inst.pack_source
    instances.save(inst)
    meta["undone"] = True
    atomicio.write_text(snap / "meta.json", json.dumps(meta, indent=2))
    return restored, problems, (snap / "saves") if (snap / "saves").is_dir() else None
