"""
mod_updater.py - checks an instance's mods for newer builds (same Minecraft version + same loader) and installs
the ones you pick.

How a mod is recognized: by the hash of the jar actually on disk, not by its file name.
  * Modrinth:   sha1 of each jar -> /version_files (what it is now) and /version_files/update (newest build that
                fits this Minecraft version and loader).
  * CurseForge: only for jars Modrinth didn't know, and only with an API key: CurseForge's own fingerprint ->
                /fingerprints, then the newest compatible file among that mod's latestFiles. Best effort - the
                CurseForge half has not been run against the live API from the build environment.

Safety: new files are downloaded and hash-checked BEFORE anything on disk changes; the old jar is moved to
<instance>\\previous_mods\\ (never deleted); every batch is logged so undo_last() can put it back exactly.
Beta/alpha builds are never pre-selected. Nothing here crosses Minecraft versions or loaders.
"""
import hashlib
import json
import shutil
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import core
import mod_doctor
import packs

MODRINTH = "https://api.modrinth.com/v2"
CURSEFORGE = "https://api.curseforge.com/v1"
UA = {"User-Agent": "Hebbyk/voidbox-launcher (mod updater)"}   # Modrinth asks for an identifying User-Agent
HISTORY_NAME = "update_history.json"
PREVIOUS_DIRNAME = "previous_mods"
CF_RELEASE_TYPES = {1: "release", 2: "beta", 3: "alpha"}
LOADERS = ("fabric", "quilt", "forge", "neoforge")


class UpdateError(Exception):
    pass


@dataclass
class Update:
    jar: str                  # file name currently installed
    title: str
    source: str               # "modrinth" | "curseforge"
    old_version: str
    new_version: str
    channel: str              # "release" | "beta" | "alpha"
    filename: str             # file name of the new build
    url: str | None           # None = the author blocks automatic downloads
    sha1: str | None = None
    size: int | None = None
    cf_ids: tuple | None = None   # (project_id, file_id) for the manifest

    @property
    def safe(self) -> bool:
        return self.channel == "release" and bool(self.url)


@dataclass
class UpdateReport:
    total: int = 0
    updates: list = field(default_factory=list)
    up_to_date: int = 0
    unknown: list = field(default_factory=list)   # jars neither service recognized
    errors: list = field(default_factory=list)
    up_to_date_names: list = field(default_factory=list)   # recognized, and the installed file already fits
    no_build_names: list = field(default_factory=list)     # recognized, but nothing exists for the target version


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def _http(url: str, payload=None, headers=None, timeout: int = 30):
    hdrs = {**UA, "Accept": "application/json", **(headers or {})}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise UpdateError(f"{url.split('?')[0]} -> HTTP {e.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise UpdateError(f"{url.split('?')[0]} -> {e}") from None


def _chunks(items, n):
    items = list(items)
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _murmur2_32(data: bytes, seed: int) -> int:
    """MurmurHash2 (32-bit). Checked against the known vector murmur2_32(bytes([1,2,3,4]), 0) == 1487941662."""
    m, r, mask = 0x5bd1e995, 24, 0xFFFFFFFF
    h = (seed ^ len(data)) & mask
    for i in range(len(data) // 4):
        k = struct.unpack_from("<I", data, i * 4)[0]
        k = (k * m) & mask
        k ^= k >> r
        k = (k * m) & mask
        h = ((h * m) & mask) ^ k
    tail = data[(len(data) // 4) * 4:]
    if len(tail) >= 3:
        h ^= tail[2] << 16
    if len(tail) >= 2:
        h ^= tail[1] << 8
    if len(tail) >= 1:
        h ^= tail[0]
        h = (h * m) & mask
    h ^= h >> 13
    h = (h * m) & mask
    h ^= h >> 15
    return h


def cf_fingerprint(data: bytes) -> int:
    """CurseForge's fingerprint: drop the whitespace bytes (tab, LF, CR, space), then MurmurHash2 with seed 1."""
    return _murmur2_32(data.translate(None, b"\t\n\r "), 1)


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------

def _primary_file(version: dict):
    files = version.get("files") or []
    return next((f for f in files if f.get("primary")), files[0] if files else None)


def _cf_best(match: dict, mc: str, loader: str | None, require_newer: bool = True):
    cur_date = (match.get("file") or {}).get("fileDate", "")
    best = None
    for f in match.get("latestFiles", []):
        gv = [str(g).lower() for g in f.get("gameVersions", [])]
        if mc.lower() not in gv or (loader and loader not in gv):
            continue
        if require_newer and f.get("fileDate", "") <= cur_date:
            continue
        if best is None or f.get("fileDate", "") > best.get("fileDate", ""):
            best = f
    return best


def check(inst, cf_api_key: str | None = None, progress=None, target_mc: str | None = None) -> UpdateReport:
    """inst: an instances.Instance. progress(text) is called with short status lines. Read-only.
    target_mc: look for builds for a DIFFERENT Minecraft version (used by version_change.py); every mod whose
    file differs from what fits that version becomes an Update, and mods with nothing for it land in
    no_build_names."""
    say = progress or (lambda _t: None)
    mods_dir = Path(inst.path) / "minecraft" / "mods"
    jars = sorted(mods_dir.glob("*.jar"), key=lambda p: p.name.lower()) if mods_dir.is_dir() else []
    report = UpdateReport(total=len(jars))
    if not jars:
        return report
    mc = target_mc or inst.minecraft_version
    cross = mc != inst.minecraft_version
    loader = inst.loader if inst.loader in LOADERS else None

    say("Reading mods...")
    data = {p: p.read_bytes() for p in jars}
    sha1 = {p: hashlib.sha1(b).hexdigest() for p, b in data.items()}

    say("Asking Modrinth...")
    current, latest = {}, {}
    try:
        for chunk in _chunks(set(sha1.values()), 100):
            current.update(_http(f"{MODRINTH}/version_files", {"hashes": chunk, "algorithm": "sha1"}))
            body = {"hashes": chunk, "algorithm": "sha1", "game_versions": [mc]}
            if loader:
                body["loaders"] = [loader]
            latest.update(_http(f"{MODRINTH}/version_files/update", body))
    except UpdateError as e:
        report.errors.append(f"Modrinth: {e}")
        current, latest = {}, {}

    def fine(p):
        report.up_to_date += 1
        report.up_to_date_names.append(p.name)

    def nothing(p):
        report.no_build_names.append(p.name)
        report.up_to_date += 0 if cross else 1      # a normal update check never reported "no build" separately

    unknown = []
    project_ids = set()
    for p in jars:
        cur = current.get(sha1[p])
        if cur is None:
            unknown.append(p)
            continue
        lat = latest.get(sha1[p])
        f = _primary_file(lat) if lat else None
        if not (lat and f):
            nothing(p)
            continue
        differs = lat.get("id") != cur.get("id")
        newer = lat.get("date_published", "") > cur.get("date_published", "")
        if differs and (cross or newer):
            project_ids.add(lat.get("project_id"))
            report.updates.append(Update(
                jar=p.name, title=p.stem, source="modrinth", old_version=str(cur.get("version_number", "?")),
                new_version=str(lat.get("version_number", "?")), channel=lat.get("version_type", "release"),
                filename=f["filename"], url=f.get("url"), sha1=(f.get("hashes") or {}).get("sha1"),
                size=f.get("size"), cf_ids=None))
            report.updates[-1]._project = lat.get("project_id")   # for the title lookup below
        else:
            fine(p)

    if unknown and cf_api_key:
        say("Asking CurseForge...")
        try:
            fps = {p: cf_fingerprint(data[p]) for p in unknown}
            resp = _http(f"{CURSEFORGE}/fingerprints", {"fingerprints": sorted(set(fps.values()))},
                         headers={"x-api-key": cf_api_key})
            matches = {m["file"]["fileFingerprint"]: m for m in (resp.get("data") or {}).get("exactMatches", [])
                       if (m.get("file") or {}).get("fileFingerprint") is not None}
            still_unknown = []
            for p in unknown:
                m = matches.get(fps[p])
                if m is None:
                    still_unknown.append(p)
                    continue
                best = _cf_best(m, mc, loader, require_newer=not cross)
                if best is None:
                    nothing(p)
                    continue
                sha = next((h["value"] for h in best.get("hashes", []) if h.get("algo") == 1), None)
                report.updates.append(Update(
                    jar=p.name, title=p.stem, source="curseforge",
                    old_version=str((m.get("file") or {}).get("displayName", "?")),
                    new_version=str(best.get("displayName", "?")),
                    channel=CF_RELEASE_TYPES.get(best.get("releaseType"), "release"),
                    filename=best.get("fileName"), url=best.get("downloadUrl"), sha1=sha,
                    size=best.get("fileLength"), cf_ids=(best.get("modId"), best.get("id"))))
            unknown = still_unknown
        except (UpdateError, KeyError, TypeError) as e:
            report.errors.append(f"CurseForge: {e}")
    report.unknown = [p.name for p in unknown]

    if cross:                                         # the "latest" build may be a beta: look for a stable one
        for u in [u for u in report.updates if u.source == "modrinth" and u.channel != "release"]:
            try:
                q = (f"loaders={urllib.parse.quote(json.dumps([loader] if loader else []))}"
                     f"&game_versions={urllib.parse.quote(json.dumps([mc]))}")
                vers = _http(f"{MODRINTH}/project/{getattr(u, '_project', '')}/version?{q}")
                stable = next((v for v in vers if v.get("version_type") == "release" and _primary_file(v)), None)
                if stable:
                    f = _primary_file(stable)
                    u.new_version, u.channel = str(stable.get("version_number", "?")), "release"
                    u.filename, u.url, u.size = f["filename"], f.get("url"), f.get("size")
                    u.sha1 = (f.get("hashes") or {}).get("sha1")
            except (UpdateError, KeyError, TypeError):
                pass                                  # keep the beta, clearly tagged

    if project_ids:                                   # nicer names than file names
        try:
            ids = json.dumps(sorted(i for i in project_ids if i))
            titles = {pr["id"]: pr.get("title") for pr in _http(f"{MODRINTH}/projects?ids={urllib.parse.quote(ids)}")}
            for u in report.updates:
                u.title = titles.get(getattr(u, "_project", None)) or u.title
        except (UpdateError, KeyError, TypeError):
            pass
    report.updates.sort(key=lambda u: u.title.lower())
    return report


# ---------------------------------------------------------------------------
# Applying + undo
# ---------------------------------------------------------------------------

def _unique(path: Path) -> Path:
    n, p = 2, path
    while p.exists():
        p = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return p


def _history_path(root) -> Path:
    return Path(root) / HISTORY_NAME


def _load_history(root) -> list:
    try:
        return json.loads(_history_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def has_history(instance_path) -> bool:
    return bool(_load_history(instance_path))


def apply(inst, updates, progress=None):
    """Installs the given Update objects. Returns (done: list[str], failed: list[(jar, reason)]).
    A mod whose download fails or doesn't verify is left exactly as it was."""
    say = progress or (lambda _t: None)
    root = Path(inst.path)
    mods, prev, tmp = root / "minecraft" / "mods", root / PREVIOUS_DIRNAME, root / ".update_tmp"
    prev.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    done, failed, batch = [], [], []
    for i, u in enumerate(updates, 1):
        say(f"{i}/{len(updates)}: {u.title}")
        try:
            if not u.url:
                raise UpdateError("the author blocks automatic downloads - get it from the website")
            old = mods / u.jar
            if not old.is_file():
                raise UpdateError("the installed file is gone")
            if u.filename != u.jar and (mods / u.filename).exists():
                raise UpdateError(f"{u.filename} already exists in the mods folder")
            new_tmp = tmp / u.filename
            core.download_file(u.url, new_tmp, u.sha1, u.size)          # verifies size/hash, raises if wrong
            if not zipfile.is_zipfile(new_tmp):                         # look inside BEFORE it replaces anything
                raise UpdateError("the download isn't a valid jar file")
            jar = mod_doctor.read_jar(new_tmp)   # a jar with no mod metadata (plain library) is fine, just unchecked
            bad = mod_doctor.check_requirements([jar], inst.minecraft_version, inst.loader, inst.loader_version)
            if bad:
                raise UpdateError(f"needs {bad[0].target} {bad[0].wanted}, this instance has {bad[0].actual}")
            manifest = packs.read_manifest(root)
            old_rec = next((f for f in (manifest or {}).get("files", [])
                            if f["path"].replace("\\", "/") == f"mods/{u.jar}"), None)
            stash = _unique(prev / u.jar)
            shutil.move(str(old), str(stash))
            try:
                shutil.move(str(new_tmp), str(mods / u.filename))
            except OSError:
                shutil.move(str(stash), str(old))                        # put the old one back
                raise
            if old_rec is not None:
                packs.remove_file_from_manifest(root, f"mods/{u.jar}")
                packs.add_file_to_manifest(
                    root, packs.ResolvedFile(path=f"mods/{u.filename}", url=u.url, sha1=u.sha1, size=u.size,
                                             curseforge_project_id=(u.cf_ids or (None, None))[0],
                                             curseforge_file_id=(u.cf_ids or (None, None))[1]),
                    name=inst.name, minecraft_version=inst.minecraft_version,
                    loader=inst.loader, loader_version=inst.loader_version)
            batch.append({"old": u.jar, "new": u.filename, "stash": stash.name, "old_record": old_rec})
            done.append(u.jar)
        except (UpdateError, OSError, RuntimeError) as e:
            failed.append((u.jar, str(e)))
    shutil.rmtree(tmp, ignore_errors=True)
    if batch:
        hist = _load_history(root)[-19:] + [{"time": int(time.time()), "items": batch}]
        _history_path(root).write_text(json.dumps(hist, indent=2), encoding="utf-8")
    return done, failed


def undo_last(inst):
    """Reverts the most recent batch: new jar out, old jar back from previous_mods. Returns (restored, problems)."""
    root = Path(inst.path)
    hist = _load_history(root)
    if not hist:
        return [], []
    batch = hist.pop()
    mods, prev = root / "minecraft" / "mods", root / PREVIOUS_DIRNAME
    restored, problems = [], []
    for it in reversed(batch["items"]):
        new, old, stash = mods / it["new"], mods / it["old"], prev / it["stash"]
        if not stash.is_file():
            problems.append(f"{it['old']}: the saved copy is gone")
            continue
        if old.exists() and it["old"] != it["new"]:
            problems.append(f"{it['old']}: a file with that name is already in the mods folder")
            continue
        try:
            if new.exists():
                new.unlink()                      # our own verified download; the old jar is what matters now
            shutil.move(str(stash), str(old))
            packs.remove_file_from_manifest(root, f"mods/{it['new']}")
            if it.get("old_record"):
                packs.add_file_to_manifest(root, packs.ResolvedFile(**it["old_record"]), name=inst.name,
                                           minecraft_version=inst.minecraft_version, loader=inst.loader,
                                           loader_version=inst.loader_version)
            restored.append(it["old"])
        except OSError as e:
            problems.append(f"{it['old']}: {e}")
    _history_path(root).write_text(json.dumps(hist, indent=2), encoding="utf-8")
    return restored, problems


if __name__ == "__main__":
    import sys
    import instances
    import settings
    if len(sys.argv) < 2:
        sys.exit('usage: py mod_updater.py "<instance name>"      (read-only: only prints what it found)')
    inst = instances.get(sys.argv[1])
    if not inst:
        sys.exit(f"No instance named '{sys.argv[1]}'")
    rep = check(inst, settings.get_curseforge_api_key(), progress=print)
    print(f"\n{rep.total} mods | {len(rep.updates)} updates | {rep.up_to_date} up to date | {len(rep.unknown)} not recognized")
    for u in rep.updates:
        flag = "" if u.safe else "   <-- " + (u.channel if u.url else "no direct download")
        print(f"  [{u.source}] {u.title}: {u.old_version} -> {u.new_version}{flag}")
    for e in rep.errors:
        print("  ERROR:", e)
    if rep.unknown:
        print("  not recognized:", ", ".join(rep.unknown[:15]) + (" ..." if len(rep.unknown) > 15 else ""))
