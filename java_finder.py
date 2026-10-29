"""
mc_launcher.java_finder — picks the right Java for a given Minecraft version
automatically, the way the real Minecraft Launcher does, instead of blindly
using whatever 'java' resolves to on PATH.

Mojang's own version JSON says exactly which major Java version a version
needs (javaVersion.majorVersion — e.g. 17 for 1.20.1, 21 for newer). This
scans likely install locations for a JDK matching that version.

If nothing suitable is installed, it downloads a Temurin JRE from Adoptium into
%LOCALAPPDATA%\\MCLauncher\\runtime\\ (never touches system folders), checking the
SHA-256 checksum Adoptium publishes before anything is unpacked or run. A
managed copy is reused on later launches, so the download happens once.
"""
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

DEFAULT_JAVA_MAJOR = 8  # pre-1.17 versions' manifests omit javaVersion entirely

RUNTIME_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MCLauncher" / "runtime"
ADOPTIUM_LTS = (8, 11, 17, 21, 25)  # Adoptium builds for these; e.g. Java 16 runs fine on 17
_UA = {"User-Agent": "VoidboxLauncher"}


def get_required_java_major(version_info: dict) -> int:
    return version_info.get("javaVersion", {}).get("majorVersion", DEFAULT_JAVA_MAJOR)


def _mojang_bundled_runtime_candidates() -> list[Path]:
    """Mojang's official launcher pre-downloads exactly-matching runtimes
    here if the person has ever run it — the most reliable source if present.
    Layout: .minecraft/runtime/<component>/<platform>/<component>/bin/"""
    mc_dir = Path(os.environ.get("APPDATA", Path.home())) / ".minecraft" / "runtime"
    if not mc_dir.exists():
        return []
    candidates = []
    for component_dir in mc_dir.iterdir():
        candidates.extend(component_dir.glob("*/*/bin/javaw.exe"))
        candidates.extend(component_dir.glob("*/*/bin/java.exe"))
    return candidates


def _common_install_dir_candidates() -> list[Path]:
    """Standard install locations for a few widely-used JDK distributions."""
    roots = [
        Path(r"C:\Program Files\Java"),
        Path(r"C:\Program Files\Eclipse Adoptium"),
        Path(r"C:\Program Files\Android\openjdk"),
        Path(r"C:\Program Files\Microsoft"),
    ]
    candidates = []
    for root in roots:
        if root.exists():
            candidates.extend(root.glob("*/bin/java.exe"))
    return candidates


def _get_major_version(java_exe: Path) -> int | None:
    """Prefers reading the JDK's own 'release' file (fast, no process spawn)
    over running 'java -version' (slower, and output format varies)."""
    release_file = java_exe.parent.parent / "release"
    if release_file.exists():
        try:
            text = release_file.read_text(errors="ignore")
            match = re.search(r'JAVA_VERSION="(?:1\.)?(\d+)', text)
            if match:
                return int(match.group(1))
        except OSError:
            pass

    try:
        result = subprocess.run([str(java_exe), "-version"], capture_output=True,
                                 text=True, timeout=5)
        output = result.stderr or result.stdout
        match = re.search(r'version "(?:1\.)?(\d+)', output)
        if match:
            return int(match.group(1))
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def find_java(required_major: int) -> str | None:
    """Returns a path to a java executable matching the required major
    version, or None if nothing on this machine matches."""
    for candidate in _mojang_bundled_runtime_candidates() + _common_install_dir_candidates():
        if _get_major_version(candidate) == required_major:
            # prefer java.exe over javaw.exe so console output stays visible
            java_exe = candidate.with_name("java.exe")
            return str(java_exe if java_exe.exists() else candidate)
    return None


def _adoptium_major(required: int) -> int:
    """Smallest Adoptium LTS that is >= the required major (16 -> 17, 18 -> 21)."""
    return next((m for m in ADOPTIUM_LTS if m >= required), required)


def _managed_java(required: int) -> str | None:
    """A JRE this launcher downloaded earlier, if it is still intact."""
    base = _adoptium_major(required)
    for d in sorted(RUNTIME_DIR.glob(f"java-{base}*"), reverse=True):
        exe = d / "bin" / "java.exe"
        if exe.exists():
            return str(exe)
    return None


def _force_rmtree(path: Path):
    """rmtree that survives Windows read-only files; never raises (caller re-checks the folder)."""
    def _fix(func, p, *_):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    try:
        shutil.rmtree(path, onexc=_fix)       # Python 3.12+
    except TypeError:
        shutil.rmtree(path, onerror=_fix)
    except OSError:
        pass


def _download_java(required: int) -> str | None:
    """Downloads + verifies + unpacks a Temurin JRE. Returns java.exe, or None on any failure."""
    major = _adoptium_major(required)
    api = (f"https://api.adoptium.net/v3/assets/latest/{major}/hotspot"
           "?os=windows&architecture=x64&image_type=jre&vendor=eclipse"
           "&release_type=ga&jvm_impl=hotspot&heap_size=normal")
    try:
        with urllib.request.urlopen(urllib.request.Request(api, headers=_UA), timeout=30) as r:
            pkg = json.load(r)[0]["binary"]["package"]
        link, want = pkg["link"], pkg["checksum"].lower()
        if len(want) != 64:
            raise ValueError("unexpected checksum format")
    except Exception as e:
        print(f"[java_finder] couldn't look up a Java {major} download: {e}")
        return None

    print(f"[java_finder] no Java {required} found - downloading Temurin JRE {major}...")
    dest = RUNTIME_DIR / f"java-{major}"
    stage = "preparing"
    try:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=RUNTIME_DIR) as tmp:
            zip_path = Path(tmp) / "jre.zip"
            stage = "downloading"
            sha, done, mark = hashlib.sha256(), 0, 25
            with urllib.request.urlopen(urllib.request.Request(link, headers=_UA), timeout=60) as r, \
                    open(zip_path, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                while chunk := r.read(1 << 20):
                    f.write(chunk)
                    sha.update(chunk)
                    done += len(chunk)
                    if total and done * 100 // total >= mark:
                        print(f"[java_finder] downloading Java {major}: {mark}%")
                        mark += 25
            if sha.hexdigest() != want:
                raise ValueError("checksum mismatch - download discarded")
            stage = "unpacking"
            out = Path(tmp) / "unpacked"
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(out)
            roots = [p for p in out.iterdir() if p.is_dir()]
            src = roots[0] if len(roots) == 1 else out
            stage = "installing"
            target = dest
            if dest.exists():                  # leftover/partial copy: clear it if we can
                _force_rmtree(dest)
            if dest.exists():                  # still there (locked?): install beside it instead
                target = RUNTIME_DIR / f"java-{major}-{int(time.time())}"
            shutil.move(str(src), str(target))
    except Exception as e:
        print(f"[java_finder] Java {major} download failed while {stage}: {e}")
        return None

    exe = target / "bin" / "java.exe"
    return str(exe) if exe.exists() else None


def resolve_java_path(version_info: dict, fallback: str = "java") -> str:
    """The function to actually call: finds a matching Java for this version,
    or falls back (with a warning) to whatever 'fallback' resolves to."""
    required = get_required_java_major(version_info)
    found = find_java(required) or _managed_java(required) or _download_java(required)
    if found:
        print(f"[java_finder] using Java {required} at {found}")
        return found
    print(f"[java_finder] no Java {required} found and the download failed - falling "
          f"back to '{fallback}' on PATH, which may be the wrong version. Check your "
          f"internet connection, or install a Java {required} JDK (e.g. from adoptium.net).")
    return fallback
