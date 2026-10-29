"""Wipes Voidbox Launcher's per-user data so the next start is a brand-new app.

  py reset_voidbox.py              delete everything (asks you to type DELETE first)
  py reset_voidbox.py --keep-cache same, but keep the downloaded game files
                                   (libraries/assets/jars), so nothing re-downloads
  py reset_voidbox.py --yes        skip the confirmation question

What it removes:
  1. the data folder  %LOCALAPPDATA%\\MCLauncher  (instances, settings file, game-file cache)
  2. the saved logins in Windows Credential Manager (Microsoft session + the launcher's
     other saved settings). The credential names are read from msauth.py / settings.py,
     not guessed.
It never touches: the installed app, your real .minecraft folder, or other programs'
credentials. Close Voidbox Launcher (and any running game) first.
"""
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path.home() / ".local" / "share"
    return base / "MCLauncher"


def credential_service_names() -> list[str]:
    names = []
    for module, attr in (("msauth", "KEYRING_SERVICE"), ("settings", "SERVICE")):
        try:
            value = getattr(__import__(module), attr)
            if value:
                names.append(str(value))
        except Exception as e:
            print(f"  ! couldn't read {module}.{attr} ({type(e).__name__}: {e}) - run this from the launcher folder")
    return names


def find_credentials(service_names: list[str]) -> list[str]:
    if not shutil.which("cmdkey") or not service_names:
        return []
    out = subprocess.run(["cmdkey", "/list"], capture_output=True, text=True, errors="replace").stdout
    targets = []
    for line in out.splitlines():
        # "target=" is not localized, unlike the "Target:" label (this works on any Windows language)
        m = re.search(r"target=(.+?)\s*$", line, re.IGNORECASE)
        if m and any(n.lower() in m.group(1).lower() for n in service_names):
            targets.append(m.group(1))
    return targets


def folder_size_mb(path: Path) -> float:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return total / (1024 * 1024)


def remove_tree(path: Path, failures: list):
    def handle(func, p, *_):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError as e:
            failures.append(f"{p}: {e}")
    try:
        shutil.rmtree(path, onexc=handle)
    except TypeError:  # Python < 3.12
        shutil.rmtree(path, onerror=handle)


def main():
    keep_cache = "--keep-cache" in sys.argv
    folder = data_dir()
    names = credential_service_names()
    creds = find_credentials(names)

    items = []
    if folder.exists():
        kids = [k for k in folder.iterdir() if not (keep_cache and k.name == "shared")]
        items = kids
    print("This will delete:")
    if items:
        print(f"  - {len(items)} item(s) in {folder}  (~{folder_size_mb(folder):.0f} MB)"
              + ("  [keeping the 'shared' game-file cache]" if keep_cache else ""))
    else:
        print(f"  - (nothing in {folder})")
    if creds:
        for t in creds:
            print(f"  - saved login in Credential Manager: {t}")
    else:
        print("  - (no saved logins found)")
    if not items and not creds:
        print("Already fresh. Nothing to do.")
        return

    if "--yes" not in sys.argv and input("\nType DELETE to continue: ").strip() != "DELETE":
        print("Cancelled. Nothing was deleted.")
        return

    failures = []
    for k in items:
        if k.is_dir() and not k.is_symlink():
            remove_tree(k, failures)
        else:
            try:
                k.unlink()
            except OSError as e:
                failures.append(f"{k}: {e}")
    if folder.exists() and not any(folder.iterdir()):
        folder.rmdir()
    for t in creds:
        r = subprocess.run(["cmdkey", f"/delete:{t}"], capture_output=True, text=True, errors="replace")
        if r.returncode != 0:
            failures.append(f"credential {t}: {(r.stdout or r.stderr).strip()}")

    if failures:
        print("\nSome things couldn't be removed (is Voidbox Launcher or a game still running?):")
        for f in failures[:10]:
            print("  -", f)
        sys.exit(1)
    print("\nDone. The next start is a fresh app: no instances, logged out.")


if __name__ == "__main__":
    main()
