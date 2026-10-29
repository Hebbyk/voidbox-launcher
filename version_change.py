"""
version_change.py - moves an instance to another Minecraft version IN PLACE (same instance, same worlds), the
way Prism/MultiMC do, but with a rollback snapshot so it can be undone.

What changes: for every mod it asks Modrinth (and CurseForge, for jars Modrinth didn't know) for a build that
fits the target Minecraft version and the instance's loader.
    keep      - the installed file already works for the target version
    replace   - a different file fits; it is downloaded, checked, and swapped in
    missing   - recognized, but nothing exists for the target version; it is moved OUT of mods\\ (it would crash
                the game) into the snapshot
    unknown   - not recognized (added by hand); left alone, and reported
The loader is moved to a matching version (same loader only; Forge <-> NeoForge is not attempted).

Safety: everything it touches is first saved under <instance>\\rollback\\<time>\\ (old mods, configs, the
manifest, optionally a full copy of the worlds). undo() puts mods/configs/version settings back. Worlds are never
modified by this module - but Minecraft itself may upgrade a world's files the first time it opens it on a newer
version, which is why backing them up first is offered (and on by default).

duplicate_instance() is the separate, conventional "copy this instance" for keeping the old version as well.
"""
import json
import re
import shutil
import time
import urllib.parse
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import core
import forge
import instances
import loaders
import mod_doctor
import mod_updater as mu
import packs

ROLLBACK_DIRNAME = "rollback"
SKIP_ON_DUPLICATE = {ROLLBACK_DIRNAME, ".update_tmp", ".vc_tmp"}


class VersionChangeError(Exception):
    pass


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

def release_versions() -> list[str]:
    """Release versions from Mojang's manifest, newest first."""
    return [v["id"] for v in core.get_version_manifest()["versions"] if v.get("type") == "release"]


def resolve_loader_version(loader: str, mc: str) -> str:
    """The loader version to use on `mc`. Raises VersionChangeError if that loader has no build for it yet."""
    try:
        if loader == "vanilla":
            return "latest"
        if loader == "neoforge":
            return forge.get_neoforge_version(mc, "latest")
        if loader == "forge":
            return forge.get_forge_version(mc, "recommended")
        if loader in ("fabric", "quilt"):
            base = loaders.FABRIC_META if loader == "fabric" else loaders.QUILT_META
            if not loaders._fetch_json(f"{base}/{urllib.parse.quote(mc)}"):
                raise loaders.LoaderError("no builds")
            return "latest"          # resolved to a stable build at launch, same as for new instances
    except (forge.ForgeError, loaders.LoaderError, OSError) as e:
        raise VersionChangeError(f"There is no {loader} for Minecraft {mc} yet ({e})") from None
    raise VersionChangeError(f"Unknown loader: {loader}")


# ---------------------------------------------------------------------------
# Plan (read-only)
# ---------------------------------------------------------------------------

@dataclass
class Plan:
    target_mc: str
    loader: str
    loader_version: str
    replace: list = field(default_factory=list)   # mod_updater.Update objects
    keep: list = field(default_factory=list)      # jar names
    missing: list = field(default_factory=list)   # jar names
    unknown: list = field(default_factory=list)   # jar names
    errors: list = field(default_factory=list)


def plan_change(inst, target_mc: str, cf_api_key=None, progress=None) -> Plan:
    if inst.minecraft_version == target_mc:
        raise VersionChangeError(f"'{inst.name}' is already on Minecraft {target_mc}")
    loader_version = resolve_loader_version(inst.loader, target_mc)
    rep = mu.check(inst, cf_api_key, progress, target_mc=target_mc)
    plan = Plan(target_mc, inst.loader, loader_version, replace=rep.updates, keep=rep.up_to_date_names,
                missing=rep.no_build_names, unknown=rep.unknown, errors=rep.errors)
    if rep.total and rep.errors and not (plan.replace or plan.keep or plan.missing):
        raise VersionChangeError("Couldn't look the mods up (" + "; ".join(rep.errors) + "). Check your connection.")
    return plan


# ---------------------------------------------------------------------------
# Copy helper (worlds backup + duplicate)
# ---------------------------------------------------------------------------

def tree_size(path: Path, skip=frozenset()) -> int:
    total = 0
    for f in Path(path).rglob("*"):
        try:
            if f.is_file() and not (set(f.relative_to(path).parts[:1]) & set(skip)):
                total += f.stat().st_size
        except OSError:
            pass
    return total


def copy_tree(src: Path, dest: Path, on_progress=None, skip=frozenset()):
    """Copies src into dest (created). on_progress(done_bytes, total_bytes). Removes a half-copied dest on failure."""
    src, dest = Path(src), Path(dest)
    files = [f for f in src.rglob("*") if f.is_file() and not (set(f.relative_to(src).parts[:1]) & set(skip))]
    total, done = sum(f.stat().st_size for f in files), 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(dest.parent).free
    if free < total * 1.05:
        raise VersionChangeError(f"Not enough free disk space: need about {total * 1.05 / 1e6:,.0f} MB, "
                                 f"have {free / 1e6:,.0f} MB.")
    try:
        dest.mkdir(parents=True, exist_ok=True)
        for d in (p for p in src.rglob("*") if p.is_dir() and not (set(p.relative_to(src).parts[:1]) & set(skip))):
            (dest / d.relative_to(src)).mkdir(parents=True, exist_ok=True)
        for f in files:
            out = dest / f.relative_to(src)
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(f, "rb") as a, open(out, "wb") as b:
                while chunk := a.read(4 << 20):
                    b.write(chunk)
                    done += len(chunk)
                    if on_progress:
                        on_progress(done, total)
            shutil.copystat(f, out)
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise


# ---------------------------------------------------------------------------
# Apply + undo
# ---------------------------------------------------------------------------

@dataclass
class ApplyResult:
    replaced: list = field(default_factory=list)
    removed: list = field(default_factory=list)       # (jar, reason)
    kept: list = field(default_factory=list)          # incompatible jars deliberately left in the mods folder (keep_incompatible)
    snapshot: Path | None = None
    worlds_backup: Path | None = None


def _write_manifest(root: Path, manifest: dict):
    (Path(root) / packs.MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def apply(inst, plan: Plan, backup_worlds: bool = True, progress=None, on_copy_progress=None,
          keep_incompatible: bool = False) -> ApplyResult:
    """keep_incompatible=True leaves mods that have no build for the target version (and ones whose replacement
    couldn't be installed) in the mods folder instead of moving them out. They often still load; when they don't, the
    game may refuse to start - that is the user's call, and undo() still works the same."""
    say = progress or (lambda _t: None)
    inst = instances.get(inst.name)
    if inst is None:
        raise VersionChangeError("That instance no longer exists")
    if inst.minecraft_version == plan.target_mc:
        raise VersionChangeError("The instance is already on that version")
    root = Path(inst.path)
    mc_dir, mods = root / "minecraft", root / "minecraft" / "mods"
    stamp, n = time.strftime("%Y%m%d-%H%M%S"), 2
    snap = root / ROLLBACK_DIRNAME / stamp
    while snap.exists():                      # never reuse a snapshot folder (two changes in one second, undo + redo)
        snap = root / ROLLBACK_DIRNAME / f"{stamp}-{n}"
        n += 1
    snap_mods, tmp = snap / "mods", root / ".vc_tmp"
    snap_mods.mkdir(parents=True, exist_ok=True)
    result = ApplyResult(snapshot=snap)
    meta = {"time": int(time.time()), "undone": False, "target_mc": plan.target_mc,
            "from_mc": inst.minecraft_version, "from_loader_version": inst.loader_version,
            "replaced": [], "removed": [], "had_manifest": False, "worlds_backup": False}

    def save_meta():
        (snap / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    try:
        say("Saving a rollback snapshot...")
        if (mc_dir / "config").is_dir():
            shutil.copytree(mc_dir / "config", snap / "config")
        if (root / packs.MANIFEST_NAME).is_file():
            shutil.copy2(root / packs.MANIFEST_NAME, snap / packs.MANIFEST_NAME)
            meta["had_manifest"] = True
        if backup_worlds and (mc_dir / "saves").is_dir():
            say("Backing up worlds...")
            copy_tree(mc_dir / "saves", snap / "saves", on_copy_progress)
            result.worlds_backup, meta["worlds_backup"] = snap / "saves", True
        save_meta()

        # 1) download + check every replacement BEFORE touching the mods folder
        say("Downloading new builds...")
        tmp.mkdir(parents=True, exist_ok=True)
        ready, failed = [], []
        for i, u in enumerate(plan.replace, 1):
            say(f"{i}/{len(plan.replace)}: {u.title}")
            try:
                if not u.url:
                    raise mu.UpdateError("the author blocks automatic downloads")
                if u.filename != u.jar and (mods / u.filename).exists():
                    raise mu.UpdateError(f"{u.filename} already exists in the mods folder")
                dl = tmp / u.filename
                core.download_file(u.url, dl, u.sha1, u.size)
                if not zipfile.is_zipfile(dl):
                    raise mu.UpdateError("the download isn't a valid jar file")
                bad = mod_doctor.check_requirements([mod_doctor.read_jar(dl)], plan.target_mc, plan.loader,
                                                    plan.loader_version)
                if bad:
                    raise mu.UpdateError(f"needs {bad[0].target} {bad[0].wanted}, the new loader is {bad[0].actual}")
                ready.append((u, dl))
            except (mu.UpdateError, OSError, RuntimeError) as e:
                failed.append((u.jar, str(e)))

        # 2) swap (meta is saved even if something throws halfway, so undo() can still put things back)
        say("Applying...")
        manifest = packs.read_manifest(root)
        records = {f["path"].replace("\\", "/"): f for f in (manifest or {}).get("files", [])}
        new_records, dropped = [], set()
        try:
            for u, dl in ready:
                old_rec = records.get(f"mods/{u.jar}")
                shutil.move(str(mods / u.jar), str(snap_mods / u.jar))
                meta["replaced"].append({"old": u.jar, "new": u.filename})
                shutil.move(str(dl), str(mods / u.filename))
                result.replaced.append(u.jar)
                if old_rec is not None:
                    dropped.add(f"mods/{u.jar}")
                    new_records.append(asdict(packs.ResolvedFile(
                        path=f"mods/{u.filename}", url=u.url, sha1=u.sha1, size=u.size,
                        curseforge_project_id=(u.cf_ids or (None, None))[0],
                        curseforge_file_id=(u.cf_ids or (None, None))[1])))
            for name, why in [(n, "no build for " + plan.target_mc) for n in plan.missing] + failed:
                if keep_incompatible:
                    result.kept.append(name)
                elif (mods / name).is_file():
                    shutil.move(str(mods / name), str(snap_mods / name))
                    meta["removed"].append(name)
                    result.removed.append((name, why))
                    dropped.add(f"mods/{name}")

            # 3) the instance's own settings + manifest
            inst.minecraft_version = plan.target_mc
            if plan.loader in ("forge", "neoforge"):
                inst.loader_version = plan.loader_version
            instances.save(inst)
            if manifest is not None:
                manifest["minecraft_version"] = plan.target_mc
                if plan.loader in ("forge", "neoforge"):
                    manifest["loader_version"] = plan.loader_version
                manifest["files"] = [f for p, f in records.items() if p not in dropped] + new_records
                _write_manifest(root, manifest)
        finally:
            save_meta()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return result


def latest_snapshot(inst) -> Path | None:
    base = Path(inst.path) / ROLLBACK_DIRNAME
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
    """Reverts the most recent version change. Returns (restored mod names, problems, worlds backup path or None).
    Worlds are NOT rolled back automatically - that would erase anything you played since; the backup (if one
    was made) is left where it is for you to copy back if you want it."""
    inst = instances.get(inst.name) or inst
    snap = latest_snapshot(inst)
    if snap is None:
        return [], [], None
    root, meta = Path(inst.path), json.loads((snap / "meta.json").read_text(encoding="utf-8"))
    mods, snap_mods = root / "minecraft" / "mods", snap / "mods"
    restored, problems = [], []
    for it in meta["replaced"]:
        (mods / it["new"]).unlink(missing_ok=True)               # our own verified download
    for name in [it["old"] for it in meta["replaced"]] + meta["removed"]:
        src = snap_mods / name
        if not src.is_file():
            problems.append(f"{name}: the saved copy is gone")
        elif (mods / name).exists():
            problems.append(f"{name}: a file with that name is already in the mods folder")
        else:
            shutil.move(str(src), str(mods / name))
            restored.append(name)
    if (snap / "config").is_dir():
        shutil.copytree(snap / "config", root / "minecraft" / "config", dirs_exist_ok=True)
    if meta.get("had_manifest") and (snap / packs.MANIFEST_NAME).is_file():
        shutil.copy2(snap / packs.MANIFEST_NAME, root / packs.MANIFEST_NAME)
    inst.minecraft_version = meta["from_mc"]
    inst.loader_version = meta["from_loader_version"]
    instances.save(inst)
    meta["undone"] = True
    (snap / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return restored, problems, (snap / "saves") if (snap / "saves").is_dir() else None


# ---------------------------------------------------------------------------
# Duplicate (the separate, conventional "copy this instance")
# ---------------------------------------------------------------------------

_BAD_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def duplicate_instance(inst, new_name: str, on_progress=None):
    """Copies the whole instance (mods, configs, worlds - everything except rollback snapshots) under a new name."""
    new_name = new_name.strip()
    if not new_name or _BAD_NAME.search(new_name) or new_name.endswith("."):
        raise VersionChangeError("That name can't be used as a folder name")
    if any(n.lower() == new_name.lower() for n in instances.load_all()):
        raise VersionChangeError(f"An instance named '{new_name}' already exists")
    src = Path(inst.path)
    dest = src.parent / new_name
    if dest.exists():
        raise VersionChangeError(f"The folder {dest} already exists")
    copy_tree(src, dest, on_progress, skip=SKIP_ON_DUPLICATE)
    icon = inst.icon_path
    if icon and str(icon).startswith(str(src)):
        icon = str(dest) + str(icon)[len(str(src)):]
    new = instances.Instance(name=new_name, path=str(dest), minecraft_version=inst.minecraft_version,
                             loader=inst.loader, loader_version=inst.loader_version,
                             pack_source=dict(inst.pack_source or {}), icon_path=icon)
    instances.save(new)
    return new


if __name__ == "__main__":
    import sys
    import settings
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    flags = {x for x in sys.argv[1:] if x.startswith("--")}
    if not a:
        sys.exit('usage:\n  py version_change.py "<instance>" <target version>            (read-only report)\n'
                 '  py version_change.py "<instance>" <target version> --apply [--no-world-backup] [--keep-incompatible]\n'
                 '  py version_change.py "<instance>" --undo\n  py version_change.py "<instance>" --duplicate "<new name>"')
    inst = instances.get(a[0])
    if not inst:
        sys.exit(f"No instance named '{a[0]}'")
    if "--undo" in flags:
        r, p, w = undo(inst)
        print(f"restored {len(r)} mods; problems: {p}; worlds backup kept at: {w}")
    elif "--duplicate" in flags:
        print("copying...")
        print("created:", duplicate_instance(inst, a[1], lambda d, t: None).path)
    elif len(a) >= 2:
        plan = plan_change(inst, a[1], settings.get_curseforge_api_key(), progress=print)
        print(f"\n{inst.name}: Minecraft {inst.minecraft_version} -> {plan.target_mc}   |   {plan.loader} -> {plan.loader_version}")
        print(f"  keep as is: {len(plan.keep)}   replace: {len(plan.replace)}   NO BUILD (would be MOVED OUT of mods, not deleted): {len(plan.missing)}   not recognized: {len(plan.unknown)}")
        for u in plan.replace:
            print(f"    replace  {u.title}: {u.old_version} -> {u.new_version}" + ("" if u.channel == "release" else f"   <-- {u.channel}") + ("" if u.url else "   (no direct download)"))
        for n in plan.missing:
            print(f"    NO BUILD {n}")
        for n in plan.unknown:
            print(f"    unknown  {n}")
        for e in plan.errors:
            print("  ERROR:", e)
        if "--apply" in flags:
            if input(f"\nChange '{inst.name}' to {plan.target_mc} now? Type 'yes': ").strip().lower() != "yes":
                sys.exit("Cancelled, nothing changed.")
            res = apply(inst, plan, backup_worlds="--no-world-backup" not in flags, progress=print,
                        keep_incompatible="--keep-incompatible" in flags)
            print(f"\nDone. replaced {len(res.replaced)}, removed {len(res.removed)}: {res.removed}, kept anyway: {res.kept}\nSnapshot: {res.snapshot}")
            print("Undo with:  py version_change.py \"%s\" --undo" % inst.name)
