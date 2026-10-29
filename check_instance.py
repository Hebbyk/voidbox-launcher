"""
check_instance.py - find out why an instance crashes on launch (stale jars / wrong loader).

    py check_instance.py "The Broken Script"           (read-only report)
    py check_instance.py "The Broken Script" --clean   (MOVES stale jars to mods_stale\\, never deletes)

"Stale" = a .jar in mods\\ that is NOT listed in the instance's pack_manifest.json
(i.e. not part of the pack you installed and not added through the launcher).
"""
import json
import os
import shutil
import sys
from pathlib import Path


def jar_names(obj, out):
    if isinstance(obj, dict):
        for v in obj.values():
            jar_names(v, out)
    elif isinstance(obj, list):
        for v in obj:
            jar_names(v, out)
    elif isinstance(obj, str) and obj.lower().endswith(".jar"):
        out.add(obj.replace("\\", "/").rsplit("/", 1)[-1].lower())


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    clean = "--clean" in sys.argv
    if not args:
        sys.exit('usage: py check_instance.py "<instance name>" [--clean]')
    name = args[0]
    root = Path(os.environ["LOCALAPPDATA"]) / "MCLauncher"
    inst = root / "instances" / name
    mods = inst / "minecraft" / "mods"
    if not mods.is_dir():
        sys.exit(f"No mods folder at {mods}")

    # 1) what the launcher thinks this instance is
    reg = root / "instances.json"
    if reg.exists():
        try:
            data = json.loads(reg.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("instances", data)
            entries = items.values() if isinstance(items, dict) else items
            for e in entries:
                if isinstance(e, dict) and e.get("name") == name:
                    print("Registry entry:", {k: v for k, v in e.items() if k != "icon_path"})
        except Exception as ex:
            print("(couldn't read instances.json:", ex, ")")
    else:
        print("(no instances.json found at", reg, ")")

    # 2) which jars belong to the pack
    pm = inst / "pack_manifest.json"
    wanted = set()
    if pm.exists():
        jar_names(json.loads(pm.read_text(encoding="utf-8")), wanted)
    print(f"pack_manifest.json lists {len(wanted)} jars" if pm.exists() else "NO pack_manifest.json for this instance")

    present = sorted(p for p in mods.iterdir() if p.is_file() and p.suffix.lower() == ".jar")
    print(f"mods\\ contains {len(present)} jars")
    if not wanted:
        sys.exit("Can't tell which jars are stale without a manifest - nothing changed.")
    stale = [p for p in present if p.name.lower() not in wanted]
    missing = sorted(wanted - {p.name.lower() for p in present})
    print(f"\nSTALE (in mods\\, not in the pack): {len(stale)}")
    for p in stale:
        print("   ", p.name)
    if missing:
        print(f"\nIn the pack but missing from mods\\: {len(missing)}")
        for m in missing[:20]:
            print("   ", m)

    if clean and stale:
        dest = inst / "minecraft" / "mods_stale"
        dest.mkdir(exist_ok=True)
        for p in stale:
            shutil.move(str(p), str(dest / p.name))
        print(f"\nMoved {len(stale)} jars to {dest}  (move them back if something breaks)")
    elif stale:
        print("\nRe-run with --clean to move these out of mods\\ (reversible).")


if __name__ == "__main__":
    main()
