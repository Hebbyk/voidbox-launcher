"""
atomic_writes.py - one-time script. Run from C:\\MCLauncher:   py atomic_writes.py

Stability step 1 of 3 (1.1.4): config files can no longer be left half-written.
  - creates atomicio.py (write to a temp file, then swap it in)
  - instances.py : the instance registry is written atomically, keeps instances.json.bak,
                   and if instances.json ever turns out corrupt it falls back to the .bak
                   (or sets the broken file aside) instead of crashing the launcher
  - i18n.py, packs.py, version_change.py, mod_updater.py : same atomic write
Nothing is changed unless ALL edits match exactly. Backups: <file>.bak. LF and CRLF both fine.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

ATOMICIO = '''"""
atomicio - write a text file so a crash or power cut can never leave it half-written.
The new content goes to "<name>.tmp" first, then replaces the real file in one step.
"""
import json
import os
import shutil
import time
from pathlib import Path


def write_text(path, text, encoding="utf-8", backup=False):
    """Atomic replacement for Path.write_text. backup=True first keeps the previous
    copy as "<name>.bak", but only if that copy is valid JSON (so a broken file never
    overwrites a good backup)."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if backup and path.exists():
            try:
                json.loads(path.read_text(encoding=encoding))
                shutil.copy2(path, path.with_name(path.name + ".bak"))
            except (OSError, ValueError):
                pass
        for attempt in range(6):  # antivirus / indexers can hold the file for a moment on Windows
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.1 * (attempt + 1))
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
'''

LOAD_OLD = '''def load_all() -> dict[str, Instance]:
    path = _registry_path()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {name: Instance(**data) for name, data in raw.items()}
'''
LOAD_NEW = '''def load_all() -> dict[str, Instance]:
    path = _registry_path()
    if not path.exists():
        return {}
    raw = None
    for candidate in (path, path.with_name(path.name + ".bak")):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            raw = data
            if candidate is not path:
                print("[instances] instances.json was unreadable - loaded the last good backup")
            break
    if raw is None:
        # Unreadable and no usable backup: keep the broken file for manual recovery, start empty.
        try:
            path.replace(path.with_name(f"{path.name}.corrupt-{int(time.time())}"))
        except OSError:
            pass
        print("[instances] instances.json was unreadable - set aside as instances.json.corrupt-*")
        return {}
    return {name: Instance(**data) for name, data in raw.items()}
'''
SAVE_OLD = '''    path.write_text(json.dumps({name: asdict(inst) for name, inst in registry.items()}, indent=2),
                     encoding="utf-8")
'''
SAVE_NEW = '''    atomicio.write_text(path, json.dumps({name: asdict(inst) for name, inst in registry.items()}, indent=2),
                        backup=True)
'''

# file -> list of (old, new, expected_count)
EDITS = {
    "instances.py": [
        ("import tempfile\nimport zipfile\n", "import tempfile\nimport time\nimport zipfile\n", 1),
        ("\nimport core\n", "\nimport atomicio\nimport core\n", 1),
        (LOAD_OLD, LOAD_NEW, 1),
        (SAVE_OLD, SAVE_NEW, 1),
    ],
    "i18n.py": [
        ("import sys\nfrom pathlib import Path\n", "import sys\nfrom pathlib import Path\n\nimport atomicio\n", 1),
        ("        config_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding=\"utf-8\")\n",
         "        atomicio.write_text(config_path(), json.dumps(data, indent=2, ensure_ascii=False))\n", 1),
    ],
    "packs.py": [
        ("\nimport core  # reuses", "\nimport atomicio\nimport core  # reuses", 1),
        ("    path.write_text(json.dumps(data, indent=2), encoding=\"utf-8\")\n",
         "    atomicio.write_text(path, json.dumps(data, indent=2))\n", 1),
        ("(Path(instance_root) / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2),\n"
         "                                                      encoding=\"utf-8\")\n",
         "atomicio.write_text(Path(instance_root) / MANIFEST_NAME, json.dumps(manifest, indent=2))\n", 2),
    ],
    "version_change.py": [
        ("\nimport core\nimport forge\n", "\nimport atomicio\nimport core\nimport forge\n", 1),
        ("(Path(root) / packs.MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding=\"utf-8\")",
         "atomicio.write_text(Path(root) / packs.MANIFEST_NAME, json.dumps(manifest, indent=2))", 1),
        ("(snap / \"meta.json\").write_text(json.dumps(meta, indent=2), encoding=\"utf-8\")",
         "atomicio.write_text(snap / \"meta.json\", json.dumps(meta, indent=2))", 2),
    ],
    "mod_updater.py": [
        ("\nimport cf_net\nimport core\n", "\nimport atomicio\nimport cf_net\nimport core\n", 1),
        ("_history_path(root).write_text(json.dumps(hist, indent=2), encoding=\"utf-8\")",
         "atomicio.write_text(_history_path(root), json.dumps(hist, indent=2))", 2),
    ],
}


def read(path):
    with open(path, "rb") as f:
        raw = f.read()
    return raw.decode("utf-8").replace("\r\n", "\n"), b"\r\n" in raw


def write(path, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def main():
    problems, planned = [], []
    if os.path.exists(os.path.join(HERE, "atomicio.py")):
        problems.append("atomicio.py already exists (already applied?)")
    for name, edits in EDITS.items():
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            problems.append(f"{name}: not found")
            continue
        text, crlf = read(p)
        for old, new, count in edits:
            if text.count(old) != count:
                problems.append(f"{name}: expected {count} match(es), found {text.count(old)} for: {old.strip().splitlines()[0][:70]}")
                break
            text = text.replace(old, new)
        else:
            planned.append((p, text, crlf))
    if problems:
        print("NOTHING CHANGED. Problems:")
        for pr in problems:
            print("  -", pr)
        sys.exit(1)

    with open(os.path.join(HERE, "atomicio.py"), "w", encoding="utf-8", newline="") as f:
        f.write(ATOMICIO)
    print("created atomicio.py")
    for p, text, crlf in planned:
        with open(p, "rb") as f, open(p + ".bak", "wb") as b:
            b.write(f.read())
        write(p, text, crlf)
        print("patched", os.path.basename(p))
    print("\nDone. Next: py -m py_compile atomicio.py instances.py i18n.py packs.py version_change.py mod_updater.py")


if __name__ == "__main__":
    main()
