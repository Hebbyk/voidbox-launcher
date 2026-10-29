"""
mod_doctor.py - finds problems inside an instance's mods\\ folder by reading what each jar says about itself,
not by guessing from file names:

  * duplicates  - two jars declaring the same mod id (e.g. an old and a new copy of the same mod)
  * requirements - a mod that needs a newer NeoForge than the instance has

Fixing duplicates never deletes anything: the older copies move to <instance>\\disabled_mods\\ (a sibling of
minecraft\\, so exports never pick them up) and can be restored with restore_all().
"""
import io
import json
import re
import shutil
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

DISABLED_DIRNAME = "disabled_mods"
_QUAL = {"snapshot": 0, "alpha": 0, "a": 0, "beta": 1, "b": 1, "pre": 1, "rc": 2, "cr": 2}


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

def vkey(v: str):
    """Sort key for mod/game versions: numbers compare as numbers (6.3.10 > 6.3.8), and a
    -beta/-rc/-alpha tail sorts before the plain release. Good enough to pick 'the newer one'."""
    m = re.search(r"\d", v or "")
    if not m:
        return ((), 0)
    nums, qual = [], None
    for tok in re.finditer(r"\d+|[A-Za-z]+", v[m.start():]):
        t = tok.group()
        if t.isdigit():
            if qual is None:
                nums.append(int(t))
        elif qual is None:
            qual = t.lower()
    while nums and nums[-1] == 0:
        nums.pop()
    return (tuple(nums), 3 if qual is None else _QUAL.get(qual, 3))


def in_range(version: str, rng: str) -> bool:
    """Maven-style range check: [21.1.262,)  (,1.22)  [1.21.1]  or a bare version (= that or newer).
    Anything it can't parse counts as satisfied - a false alarm is worse than a missed warning."""
    rng = (rng or "").strip()
    if not rng:
        return True
    k = vkey(version)
    if rng[0] in "[(":
        m = re.fullmatch(r"([\[(])\s*([^,\]\)]*?)\s*(?:,\s*([^,\]\)]*?)\s*)?([\])])", rng)
        if not m:
            return True
        lo_inc, lo, hi, hi_inc = m.group(1) == "[", m.group(2), m.group(3), m.group(4) == "]"
        if hi is None:
            return k == vkey(lo)
        if lo and (k < vkey(lo) or (k == vkey(lo) and not lo_inc)):
            return False
        if hi and (k > vkey(hi) or (k == vkey(hi) and not hi_inc)):
            return False
        return True
    return k >= vkey(rng)


# ---------------------------------------------------------------------------
# Reading jars
# ---------------------------------------------------------------------------

@dataclass
class Req:
    target: str   # modId the jar depends on, e.g. "neoforge" or "minecraft"
    range: str


@dataclass
class ModJar:
    name: str
    path: Path
    mtime: float
    mods: dict = field(default_factory=dict)   # modId -> version, for the mods this jar provides
    reqs: list = field(default_factory=list)   # requirements, including those of bundled (jar-in-jar) mods


def _read_zip(zf: zipfile.ZipFile):
    mods, reqs = {}, []
    names = set(zf.namelist())
    impl = None
    if "META-INF/MANIFEST.MF" in names:
        m = re.search(r"^Implementation-Version:\s*(.+?)\s*$",
                      zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace"), re.M)
        impl = m.group(1) if m else None

    for toml_name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
        if toml_name not in names:
            continue
        try:
            data = tomllib.loads(zf.read(toml_name).decode("utf-8", "replace"))
        except Exception:
            break
        for m in data.get("mods", []):
            ver = str(m.get("version", ""))
            if m.get("modId"):
                mods[m["modId"]] = (impl or "?") if ver.startswith("${") else (ver or "?")
        for deps in (data.get("dependencies") or {}).values():
            for d in ([deps] if isinstance(deps, dict) else deps):
                required = (d.get("type") == "required") if "type" in d else bool(d.get("mandatory", True))
                if required and d.get("modId"):
                    reqs.append(Req(d["modId"], str(d.get("versionRange", ""))))
        break

    if "fabric.mod.json" in names:
        try:
            j = json.loads(zf.read("fabric.mod.json").decode("utf-8-sig", "replace"))
            mods[j["id"]] = str(j.get("version", "?"))
        except Exception:
            pass
    if "quilt.mod.json" in names:
        try:
            q = json.loads(zf.read("quilt.mod.json").decode("utf-8-sig", "replace"))["quilt_loader"]
            mods[q["id"]] = str(q.get("version", "?"))
        except Exception:
            pass

    for n in names:   # jar-in-jar: bundled mods add requirements but are not "duplicates"
        if n.startswith("META-INF/jarjar/") and n.endswith(".jar"):
            try:
                with zipfile.ZipFile(io.BytesIO(zf.read(n))) as inner:
                    reqs += _read_zip(inner)[1]
            except Exception:
                pass
    return mods, reqs


def read_jar(p: Path) -> ModJar:
    """One jar's mod ids, versions and requirements. A file that isn't a readable zip gets no mods."""
    p = Path(p)
    try:
        with zipfile.ZipFile(p) as zf:
            mods, reqs = _read_zip(zf)
        return ModJar(p.name, p, p.stat().st_mtime, mods, reqs)
    except (zipfile.BadZipFile, OSError):
        return ModJar(p.name, p, 0.0)


def scan(mods_dir: Path) -> list[ModJar]:
    return [read_jar(p) for p in sorted(Path(mods_dir).glob("*.jar"), key=lambda p: p.name.lower())]


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------

@dataclass
class DupPlan:
    moves: list = field(default_factory=list)    # (loser ModJar, winner ModJar, mod_id)
    manual: list = field(default_factory=list)   # file names we won't touch automatically


def plan_duplicates(jars: list[ModJar]) -> DupPlan:
    by_id: dict[str, list[ModJar]] = {}
    for j in jars:
        for mid in j.mods:
            by_id.setdefault(mid, []).append(j)
    winners, losers = {}, {}
    for mid, group in by_id.items():
        if len(group) < 2:
            continue
        ranked = sorted(group, key=lambda j: (vkey(j.mods[mid]), j.mtime), reverse=True)
        winners[mid] = ranked[0]
        for l in ranked[1:]:
            losers.setdefault(l.name, (l, ranked[0], mid))
    plan = DupPlan()
    for name, (loser, winner, mid) in losers.items():
        # a jar that is the best (or only) provider of ANOTHER mod id must not be switched off automatically
        needed = any(len(by_id[m]) == 1 or winners.get(m) is loser for m in loser.mods if m != mid)
        (plan.manual if needed else plan.moves).append(name if needed else (loser, winner, mid))
    return plan


def disabled_dir(instance_path) -> Path:
    return Path(instance_path) / DISABLED_DIRNAME


def list_disabled(instance_path) -> list[str]:
    d = disabled_dir(instance_path)
    return sorted(p.name for p in d.glob("*.jar")) if d.is_dir() else []


def fix_duplicates(instance_path, plan: DupPlan):
    """Moves the older copies out of mods\\. Returns (moved names, failed names)."""
    mods_dir, dest = Path(instance_path) / "minecraft" / "mods", disabled_dir(instance_path)
    dest.mkdir(parents=True, exist_ok=True)
    moved, failed = [], []
    for loser, _winner, _mid in plan.moves:
        src, target, n = mods_dir / loser.name, dest / loser.name, 2
        while target.exists():
            target = dest / f"{Path(loser.name).stem} ({n}).jar"; n += 1
        try:
            shutil.move(str(src), str(target))
            moved.append(loser.name)
        except OSError:
            failed.append(loser.name)
    return moved, failed


def disable_mod(instance_path, filename: str) -> None:
    """Switches one mod off by moving it to disabled_mods (the same folder the duplicate fixer uses)."""
    if Path(filename).name != filename:
        raise OSError(f"Invalid mod filename: {filename}")
    src, dest = Path(instance_path) / "minecraft" / "mods" / filename, disabled_dir(instance_path)
    if not src.is_file():
        raise OSError(f"'{filename}' isn't in the mods folder")
    dest.mkdir(parents=True, exist_ok=True)
    target, n = dest / filename, 2
    while target.exists():
        target = dest / f"{Path(filename).stem} ({n}).jar"; n += 1
    shutil.move(str(src), str(target))


def enable_mod(instance_path, filename: str) -> None:
    """Switches one mod back on. Refuses if a file with that name is already in mods."""
    if Path(filename).name != filename:
        raise OSError(f"Invalid mod filename: {filename}")
    src, target = disabled_dir(instance_path) / filename, Path(instance_path) / "minecraft" / "mods" / filename
    if not src.is_file():
        raise OSError(f"'{filename}' isn't in the disabled folder")
    if target.exists():
        raise OSError(f"A mod named '{filename}' is already switched on")
    shutil.move(str(src), str(target))


def restore_all(instance_path):
    """Puts every disabled jar back. Returns (restored names, skipped names that already exist in mods\\)."""
    mods_dir = Path(instance_path) / "minecraft" / "mods"
    restored, skipped = [], []
    for name in list_disabled(instance_path):
        target = mods_dir / name
        if target.exists():
            skipped.append(name)
            continue
        shutil.move(str(disabled_dir(instance_path) / name), str(target))
        restored.append(name)
    return restored, skipped


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------

@dataclass
class Problem:
    jar: str
    target: str
    wanted: str
    actual: str


def check_requirements(jars: list[ModJar], mc_version: str, loader: str, loader_version: str) -> list[Problem]:
    """Only checks NeoForge's own version, whose number format is the same in mods.toml ranges and in the
    launcher, and which FML itself enforces (that is what the real crash logs complained about).

    Minecraft ranges are deliberately NOT checked: mods like Iris, JEI and Better ModList declare
    [1.21,1.21.1) yet load fine on 1.21.1 (they are in the working mod list of a real log), so checking them
    produced false alarms. Forge is skipped too, because its version strings can't be compared reliably."""
    have = {}
    if loader == "neoforge" and loader_version and loader_version != "latest":
        have["neoforge"] = loader_version
    out, seen = [], set()
    for j in jars:
        for r in j.reqs:
            actual = have.get(r.target)
            if actual and r.range and not in_range(actual, r.range) and (j.name, r.target, r.range) not in seen:
                seen.add((j.name, r.target, r.range))
                out.append(Problem(j.name, r.target, r.range, actual))
    return out


@dataclass
class Report:
    jars: int
    plan: DupPlan
    problems: list
    disabled: list
    scanned: list = field(default_factory=list)   # the ModJar objects, for showing versions in the UI


def analyze(inst) -> Report:
    """inst: an instances.Instance. Reads every jar in its mods folder (a couple of seconds for big packs)."""
    jars = scan(Path(inst.path) / "minecraft" / "mods")
    return Report(len(jars), plan_duplicates(jars),
                  check_requirements(jars, inst.minecraft_version, inst.loader, inst.loader_version),
                  list_disabled(inst.path), jars)
