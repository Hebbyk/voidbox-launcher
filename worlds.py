"""
worlds.py - finds Minecraft worlds on this PC (CurseForge app, the official launcher, Prism, Modrinth app,
other Voidbox instances, backup folders on Desktop/Downloads/Documents, or any folder you point at) and
COPIES one into an instance's saves\\ folder. The original is never moved or changed.
"""
import gzip
import os
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path

import mod_doctor


def read_nbt(raw: bytes):
    """Tiny NBT reader - just enough for level.dat."""
    pos = 0

    def take(fmt):
        nonlocal pos
        v = struct.unpack_from(fmt, raw, pos)[0]
        pos += struct.calcsize(fmt)
        return v

    def string():
        nonlocal pos
        n = take(">H")
        s = raw[pos:pos + n].decode("utf-8", "replace")
        pos += n
        return s

    def payload(t):
        nonlocal pos
        simple = {1: ">b", 2: ">h", 3: ">i", 4: ">q", 5: ">f", 6: ">d"}
        if t in simple:
            return take(simple[t])
        if t == 8:
            return string()
        if t == 7:
            n = take(">i"); pos += n; return None
        if t == 11:
            n = take(">i"); pos += 4 * n; return None
        if t == 12:
            n = take(">i"); pos += 8 * n; return None
        if t == 9:
            it, n = take(">b"), take(">i")
            return [payload(it) for _ in range(n)]
        if t == 10:
            d = {}
            while True:
                tt = take(">b")
                if tt == 0:
                    return d
                k = string(); d[k] = payload(tt)
        raise ValueError(f"unknown NBT tag {t}")

    t = take(">b"); string()
    return payload(t)


@dataclass
class World:
    source: str
    path: Path
    name: str
    mc_version: str
    size: int
    saved: float


def _info(w: Path):
    try:
        data = read_nbt(gzip.decompress((w / "level.dat").read_bytes()))["Data"]
        return (data.get("Version") or {}).get("Name", "?"), str(data.get("LevelName", w.name))
    except Exception:
        return "?", w.name


def _size(p: Path) -> int:
    total = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total


def _dirs(p: Path):
    try:
        return [d for d in p.iterdir() if d.is_dir()] if p.is_dir() else []
    except OSError:
        return []


def _roots(extra):
    h = Path.home()
    app = Path(os.environ.get("APPDATA", h / "AppData" / "Roaming"))
    loc = Path(os.environ.get("LOCALAPPDATA", h / "AppData" / "Local"))
    out = []
    for base in (h / "curseforge" / "minecraft" / "Instances", h / "Documents" / "curseforge" / "minecraft" / "Instances"):
        out += [(f"CurseForge: {i.name}", i / "saves") for i in _dirs(base)]
    out.append(("Minecraft launcher", app / ".minecraft" / "saves"))
    for i in _dirs(app / "PrismLauncher" / "instances"):
        out += [(f"Prism: {i.name}", i / sub / "saves") for sub in (".minecraft", "minecraft")]
    out += [(f"Modrinth app: {i.name}", i / "saves") for i in _dirs(app / "ModrinthApp" / "profiles")]
    out += [(f"Voidbox: {i.name}", i / "minecraft" / "saves") for i in _dirs(loc / "MCLauncher" / "instances")]
    for folder in ("Desktop", "Downloads", "Documents"):          # backups people made by hand
        out += [(f"{folder}: {d.name}", d) for d in _dirs(h / folder)]
    out += [("Chosen folder", Path(e)) for e in extra]
    return out


def find_worlds(target_saves: Path, extra=()) -> list[World]:
    """Every folder that has a level.dat, newest-saved first. A root that is itself a world counts too."""
    skip = {Path(target_saves).resolve()}
    found, seen = [], set()
    for label, root in _roots(extra):
        try:
            candidates = [root] if (root / "level.dat").is_file() else _dirs(root)
        except OSError:
            continue
        if root.resolve() in skip:
            continue
        for w in candidates:
            try:
                rp, lvl = w.resolve(), w / "level.dat"
                if rp in seen or rp in skip or not lvl.is_file() or w.parent.resolve() in skip:
                    continue
                seen.add(rp)
                ver, name = _info(w)
                found.append(World(label, w, name, ver, _size(w), lvl.stat().st_mtime))
            except OSError:
                continue
    return sorted(found, key=lambda x: x.saved, reverse=True)


def is_newer_than(world_version: str, game_version: str) -> bool:
    return world_version != "?" and mod_doctor.vkey(world_version) > mod_doctor.vkey(game_version)


def copy_world(src: Path, target_saves: Path, on_progress=None) -> Path:
    """Copies the world folder into target_saves (numbered if the name is taken). on_progress(done, total) in bytes.
    A half-finished copy is removed on failure so it never shows up as a broken world."""
    src, target_saves = Path(src), Path(target_saves)
    target_saves.mkdir(parents=True, exist_ok=True)
    dest, n = target_saves / src.name, 2
    while dest.exists():
        dest = target_saves / f"{src.name} ({n})"; n += 1
    files = [f for f in src.rglob("*") if f.is_file()]
    total, done = sum(f.stat().st_size for f in files), 0
    free = shutil.disk_usage(target_saves).free
    if free < total * 1.05:
        raise OSError(f"Not enough free disk space: need about {total * 1.05 / 1e6:,.0f} MB, have {free / 1e6:,.0f} MB.")
    try:
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
        for d in (p for p in src.rglob("*") if p.is_dir()):
            (dest / d.relative_to(src)).mkdir(parents=True, exist_ok=True)   # keep empty folders (e.g. empty region dirs)
        return dest
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise
