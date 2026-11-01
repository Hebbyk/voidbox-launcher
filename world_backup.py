"""
mc_launcher.world_backup - automatic world backups with one-click restore.

When you press Play, every world in the instance whose files changed since its last backup is zipped to
<instance>/world_backups/<world>/<world>_<date>.zip (uncompressed zip: worlds are already compressed, so this is
fast). The newest few are kept (default 3 per world). Restoring never deletes anything: the current world is renamed
to <world>_before_restore_<date> first. Backups live outside minecraft/ so Change version / Duplicate / exports
don't drag them along. Turn it off in Settings. Any problem here is reported, never allowed to block a launch.
"""
import json
import os
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

KEEP_DEFAULT = 3
FOLDER = "world_backups"


# ---------------------------------------------------------------- settings (config.json, shared with i18n)
def _config_path() -> Path:
    import i18n
    return i18n.config_path()


def _read_cfg() -> dict:
    try:
        d = json.loads(_config_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_cfg(updates: dict) -> None:
    cfg = _read_cfg()
    cfg.update(updates)
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)  # never leaves a half-written config behind


def is_enabled() -> bool:
    return bool(_read_cfg().get("world_backups", True))


def set_enabled(on: bool) -> None:
    try:
        _write_cfg({"world_backups": bool(on)})
    except OSError as e:
        print(f"[backup] couldn't save the setting ({type(e).__name__})")


def keep_count() -> int:
    try:
        return max(1, min(20, int(_read_cfg().get("world_backups_keep", KEEP_DEFAULT))))
    except (TypeError, ValueError):
        return KEEP_DEFAULT


# ---------------------------------------------------------------- helpers
@dataclass
class Backup:
    world: str
    path: Path
    when: float
    size: int


def _saves(inst_path) -> Path:
    return Path(inst_path) / "minecraft" / "saves"


def backups_dir(inst_path) -> Path:
    return Path(inst_path) / FOLDER


def _worlds(inst_path) -> list[Path]:
    s = _saves(inst_path)
    try:
        # "<world>_before_restore_<date>" folders are the safety copies a restore leaves behind: not backed up again
        return sorted(p for p in s.iterdir()
                      if p.is_dir() and (p / "level.dat").is_file() and "_before_restore_" not in p.name)
    except OSError:
        return []


def _walk_files(world: Path):
    for dp, _, fn in os.walk(world):
        for f in fn:
            if f != "session.lock":
                yield Path(dp) / f


def _world_state(world: Path) -> tuple[float, int]:
    """(newest file modification time, total bytes), ignoring session.lock (Minecraft touches it just by opening)."""
    newest, total = 0.0, 0
    for p in _walk_files(world):
        try:
            st = p.stat()
        except OSError:
            continue
        newest = max(newest, st.st_mtime)
        total += st.st_size
    return newest, total


def _index_path(inst_path, world_name: str) -> Path:
    return backups_dir(inst_path) / world_name / "last.json"


def _last_source_mtime(inst_path, world_name: str) -> float:
    try:
        return float(json.loads(_index_path(inst_path, world_name).read_text(encoding="utf-8")).get("src_mtime", 0))
    except (OSError, ValueError, AttributeError):
        return 0.0


# ---------------------------------------------------------------- backing up
def backup_world(inst_path, world: Path, force: bool = False, progress=None) -> Path | None:
    """Zips one world. Returns the zip, or None if nothing changed since the last backup (and not force)."""
    newest, total = _world_state(world)
    if not force and newest <= _last_source_mtime(inst_path, world.name) + 0.5:
        return None
    dest_dir = backups_dir(inst_path) / world.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(dest_dir).free
    if free < total * 1.1 + 200_000_000:
        raise OSError(f"not enough free disk space to back up '{world.name}' "
                      f"(needs about {total / 1e6:,.0f} MB, {free / 1e6:,.0f} MB free)")
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    dest = dest_dir / f"{world.name}_{stamp}.zip"
    n = 2
    while dest.exists():
        dest = dest_dir / f"{world.name}_{stamp}_{n}.zip"
        n += 1
    tmp = dest.with_name(dest.name + ".part")
    done = 0
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            for p in _walk_files(world):
                try:
                    zf.write(p, Path(world.name) / p.relative_to(world))
                    done += p.stat().st_size
                except OSError:
                    continue  # a file that vanished mid-copy (autosave) is skipped, not fatal
                if progress and total:
                    progress(min(99, int(done * 100 / total)))
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    _index_path(inst_path, world.name).write_text(json.dumps({"src_mtime": newest}), encoding="utf-8")
    _prune(inst_path, world.name)
    return dest


def _prune(inst_path, world_name: str) -> None:
    zips = sorted((backups_dir(inst_path) / world_name).glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in zips[keep_count():]:
        try:
            old.unlink()
        except OSError:
            pass


def backup_all(inst_path, force: bool = False, progress=None):
    """Backs up every changed world. Returns (new zips, number of unchanged worlds, error messages)."""
    made, unchanged, errors = [], 0, []
    for w in _worlds(inst_path):
        try:
            z = backup_world(inst_path, w, force=force, progress=progress)
            if z:
                made.append(z)
            else:
                unchanged += 1
        except Exception as e:
            errors.append(f"{w.name}: {e}")
    return made, unchanged, errors


def backup_before_launch(inst_path) -> list[Path]:
    """Called by instances.launch(). Quiet, never raises."""
    try:
        if not is_enabled():
            return []
        made, _, errors = backup_all(inst_path)
        for e in errors:
            print(f"[backup] skipped - {e}")
        if made:
            print(f"[backup] saved {len(made)} world backup(s)")
        return made
    except Exception as e:
        print(f"[backup] skipped ({type(e).__name__}: {e})")
        return []


# ---------------------------------------------------------------- listing / restoring
def list_backups(inst_path) -> list[Backup]:
    out = []
    root = backups_dir(inst_path)
    if root.is_dir():
        for z in root.glob("*/*.zip"):
            try:
                st = z.stat()
            except OSError:
                continue
            out.append(Backup(z.parent.name, z, st.st_mtime, st.st_size))
    return sorted(out, key=lambda b: b.when, reverse=True)


def restore_backup(inst_path, zip_path) -> tuple[Path, Path | None]:
    """Puts a backed-up world back into saves/. Returns (restored world folder, where the previous version was kept
    or None). Nothing is ever deleted: an existing world of the same name is renamed first."""
    saves = _saves(inst_path)
    saves.mkdir(parents=True, exist_ok=True)
    base = saves.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n and not n.endswith("/")]
        tops = {Path(n).parts[0] for n in names}
        if len(tops) != 1:
            raise ValueError("this backup doesn't look like a single world")
        world = tops.pop()
        for n in names:  # zip-slip guard: every member must land inside saves/<world>
            target = (saves / n).resolve()
            if Path(n).is_absolute() or (target != base / world and (base / world) not in target.parents):
                raise ValueError(f"unsafe path in backup: {n}")
        dest = saves / world
        kept = None
        if dest.exists():
            stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
            kept = saves / f"{world}_before_restore_{stamp}"
            k = 2
            while kept.exists():
                kept = saves / f"{world}_before_restore_{stamp}_{k}"
                k += 1
            dest.rename(kept)
        try:
            zf.extractall(saves)
        except BaseException:
            shutil.rmtree(dest, ignore_errors=True)  # undo the partial restore, then put the old world back
            if kept:
                kept.rename(dest)
            raise
    return dest, kept
