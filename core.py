"""
mc_launcher.core — bare-metal Minecraft launch engine.

Handles: version manifest, library/asset/client downloads, native extraction,
offline auth, and building+running the java launch command for VANILLA MC.

Modloaders and pack import build on top of this (loaders.py, packimport.py).
"""

# --- build metadata ---
try:
    from _canary import BUILD_TAG
except ImportError:
    BUILD_TAG = None
# --- end build metadata ---



import hashlib
import json
import os

import java_finder
import platform
import shutil
import subprocess
import threading
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

# ---------------------------------------------------------------------------
# Paths — everything lives under a root instance dir the caller supplies.
# Layout per instance:
#   <instance>/minecraft/versions/<id>/<id>.jar + <id>.json
#   <instance>/minecraft/libraries/...
#   <instance>/minecraft/assets/{indexes,objects}
#   <instance>/minecraft/natives/<version_id>/   (extracted per-launch)
#   <instance>/minecraft/mods, saves, config, resourcepacks, etc.
# ---------------------------------------------------------------------------

def get_os_name() -> str:
    s = platform.system().lower()
    if s == "windows":
        return "windows"
    if s == "darwin":
        return "osx"
    return "linux"


def get_arch() -> str:
    m = platform.machine().lower()
    if m in ("amd64", "x86_64"):
        return "x86_64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    return m


def _hash_file(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_matches(path: Path, expected_size: int | None, sha1: str | None,
                   sha256: str | None) -> bool:
    if expected_size is not None and path.stat().st_size != expected_size:
        return False
    if sha256 is not None and _hash_file(path, "sha256") != sha256:
        return False
    if sha1 is not None and _hash_file(path, "sha1") != sha1:
        return False
    return True


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) mc_launcher/0.1"


def _replace_with_retry(tmp: Path, dest: Path, expected_size, sha1, sha256,
                        attempts: int = 10, delay: float = 0.3):
    """Move a finished download into place, tolerating a briefly-locked
    destination (WinError 32: antivirus scanning the fresh file, or a
    second download of the same file finishing first). If dest is locked
    but already holds a good copy, the other writer won — just drop ours."""
    for i in range(attempts):
        try:
            os.replace(tmp, dest)
            return
        except PermissionError:
            try:
                if dest.exists() and _file_matches(dest, expected_size, sha1, sha256):
                    tmp.unlink(missing_ok=True)
                    return
            except OSError:
                pass
            if i == attempts - 1:
                raise
            time.sleep(delay)


def download_file(url: str, dest: Path, sha1: str | None = None,
                   expected_size: int | None = None, sha256: str | None = None,
                   on_progress=None):
    """on_progress(bytes_done, total_bytes) is optional; total_bytes is 0
    when the server sent no Content-Length."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if _file_matches(dest, expected_size, sha1, sha256):
            return
        print(f"[core] {dest.name} doesn't match expected size/hash (corrupt/incomplete "
              f"download or quarantined by antivirus) \u2014 re-downloading...")
        dest.unlink()
    # Unique temp name per call: two downloads of the same file (a double
    # click) used to share one ".part" and fight over the rename.
    tmp = dest.with_name(f"{dest.name}.{uuid.uuid4().hex[:8]}.part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if on_progress:
                    on_progress(done, total)
        if not _file_matches(tmp, expected_size, sha1, sha256):
            got = tmp.stat().st_size
            raise RuntimeError(
                f"Download verification failed for {url} (size/hash mismatch \u2014 "
                f"expected size {expected_size}, got {got} bytes). If this keeps "
                f"happening, check your antivirus isn't deleting files out of the "
                f"instance folder mid-download."
            )
        _replace_with_retry(tmp, dest, expected_size, sha1, sha256)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Version manifest / version info
# ---------------------------------------------------------------------------

def get_version_manifest() -> dict:
    return fetch_json(VERSION_MANIFEST_URL)


def get_version_info(version_id: str) -> dict:
    manifest = get_version_manifest()
    entry = next((v for v in manifest["versions"] if v["id"] == version_id), None)
    if not entry:
        raise ValueError(f"Unknown Minecraft version: {version_id}")
    return fetch_json(entry["url"])


# ---------------------------------------------------------------------------
# Rule evaluation (library os/arch rules, feature-gated arguments)
# ---------------------------------------------------------------------------

def rules_allow(rules: list | None, active_features: set[str] | None = None) -> bool:
    if not rules:
        return True
    active_features = active_features or set()
    allowed = False
    for rule in rules:
        action_allows = rule["action"] == "allow"
        matches = True
        os_rule = rule.get("os")
        if os_rule:
            if "name" in os_rule and os_rule["name"] != get_os_name():
                matches = False
            if "arch" in os_rule and os_rule["arch"] != get_arch():
                matches = False
        feat_rule = rule.get("features")
        if feat_rule:
            for feat, want in feat_rule.items():
                if bool(want) != (feat in active_features):
                    matches = False
        if matches:
            allowed = action_allows
    return allowed


# ---------------------------------------------------------------------------
# Libraries + natives
# ---------------------------------------------------------------------------

def maven_coord_to_path(coord: str) -> str:
    """'net.fabricmc:tiny-mappings-parser:0.2.2.14' ->
    'net/fabricmc/tiny-mappings-parser/0.2.2.14/tiny-mappings-parser-0.2.2.14.jar'
    Fabric/Quilt's own libraries are listed this old-style way (a maven
    coordinate + repo base url) instead of Mojang's direct-download format."""
    parts = coord.split(":")
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else None
    filename = f"{artifact}-{version}" + (f"-{classifier}" if classifier else "") + ".jar"
    return f"{group.replace('.', '/')}/{artifact}/{version}/{filename}"


def ensure_libraries(version_info: dict, libs_dir: Path, natives_dir: Path) -> list[str]:
    """Downloads required libraries + extracts natives. Returns classpath entries."""
    classpath = []
    os_name = get_os_name()
    natives_dir.mkdir(parents=True, exist_ok=True)

    for lib in version_info.get("libraries", []):
        if not rules_allow(lib.get("rules")):
            continue

        downloads = lib.get("downloads", {})

        artifact = downloads.get("artifact")
        if artifact:
            path = libs_dir / artifact["path"]
            download_file(artifact["url"], path, artifact.get("sha1"), artifact.get("size"))
            if str(path) not in classpath:
                classpath.append(str(path))
        elif not downloads and lib.get("name") and lib.get("url"):
            # Old-style maven-coordinate library (Fabric/Quilt's own deps)
            rel_path = maven_coord_to_path(lib["name"])
            path = libs_dir / rel_path
            base_url = lib["url"] if lib["url"].endswith("/") else lib["url"] + "/"
            download_file(base_url + rel_path, path)
            if str(path) not in classpath:
                classpath.append(str(path))

        # Old-style natives (pre ~1.19): classifiers keyed by "natives-<os>"
        natives_key = (lib.get("natives") or {}).get(os_name)
        if natives_key:
            classifier = downloads.get("classifiers", {}).get(natives_key)
            if classifier:
                native_jar = libs_dir / classifier["path"]
                download_file(classifier["url"], native_jar, classifier.get("sha1"), classifier.get("size"))
                _extract_natives(native_jar, natives_dir, lib.get("extract", {}))

    return classpath


def _extract_natives(jar_path: Path, dest: Path, extract_rules: dict):
    exclude = extract_rules.get("exclude", [])
    with zipfile.ZipFile(jar_path) as zf:
        for name in zf.namelist():
            if name.startswith("META-INF"):
                continue
            if any(name.startswith(ex) for ex in exclude):
                continue
            if name.endswith("/"):
                continue
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


# ---------------------------------------------------------------------------
# Client jar + assets
# ---------------------------------------------------------------------------

def ensure_client_jar(version_info: dict, versions_dir: Path) -> Path:
    vid = version_info["id"]
    jar_path = versions_dir / vid / f"{vid}.jar"
    client = version_info["downloads"]["client"]
    download_file(client["url"], jar_path, client.get("sha1"), client.get("size"))
    return jar_path


def ensure_assets(version_info: dict, assets_dir: Path) -> str:
    """Downloads asset index + objects. Returns the assets index id (for launch args)."""
    idx_info = version_info["assetIndex"]
    index_id = idx_info["id"]
    index_path = assets_dir / "indexes" / f"{index_id}.json"
    download_file(idx_info["url"], index_path, idx_info.get("sha1"), idx_info.get("size"))

    index = json.loads(index_path.read_text(encoding="utf-8"))
    objects_dir = assets_dir / "objects"
    for obj in index.get("objects", {}).values():
        h = obj["hash"]
        obj_path = objects_dir / h[:2] / h
        url = f"https://resources.download.minecraft.net/{h[:2]}/{h}"
        download_file(url, obj_path, h, obj.get("size"))

    return index_id


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def offline_auth(username: str) -> dict:
    """Cracked/offline profile. UUID is deterministic from 'OfflinePlayer:<name>',
    matching vanilla's own offline-mode behavior."""
    offline_uuid = uuid.uuid3(uuid.NAMESPACE_DNS, f"OfflinePlayer:{username}")
    return {
        "access_token": "0",
        "uuid": str(offline_uuid),
        "username": username,
        "user_type": "legacy",
    }


# Microsoft OAuth (premium) auth lives in msauth.py — plugs into the same
# {access_token, uuid, username, user_type: "msa"} shape.


# ---------------------------------------------------------------------------
# Launch command construction
# ---------------------------------------------------------------------------

def build_launch_command(
    instance_dir: Path,
    version_info: dict,
    classpath: list[str],
    client_jar: Path,
    natives_dir: Path,
    assets_dir: Path,
    assets_index_id: str,
    auth: dict,
    java_path: str = "java",
    memory_mb: int = 4096,
    extra_jvm_args: list[str] | None = None,
    libs_dir: Path | None = None,
) -> list[str]:
    vid = version_info["id"]
    full_classpath = list(dict.fromkeys(classpath + [str(client_jar)]))  # de-dup, keep order
    classpath_sep = ";" if get_os_name() == "windows" else ":"

    substitutions = {
        "auth_player_name": auth["username"],
        "version_name": vid,
        "game_directory": str(instance_dir / "minecraft"),
        "assets_root": str(assets_dir),
        "assets_index_name": assets_index_id,
        "auth_uuid": auth["uuid"],
        "auth_access_token": auth["access_token"],
        "user_type": auth["user_type"],
        "version_type": version_info.get("type", "release"),
        "natives_directory": str(natives_dir),
        "launcher_name": "mc_launcher",
        "launcher_version": "0.1",
        "classpath": classpath_sep.join(full_classpath),
        "auth_xuid": "0",
        "clientid": "0",
        "library_directory": str(libs_dir) if libs_dir else "",
        "classpath_separator": classpath_sep,
    }

    cmd = [java_path, f"-Xmx{memory_mb}M", f"-Djava.library.path={natives_dir}"]
    cmd += extra_jvm_args or []

    args_block = version_info.get("arguments")
    if args_block:
        cmd += _resolve_arg_list(args_block.get("jvm", []), substitutions)
    else:
        cmd += ["-cp", substitutions["classpath"]]

    main_class = version_info.get("mainClass", "net.minecraft.client.main.Main")
    cmd.append(main_class)

    if args_block:
        cmd += _resolve_arg_list(args_block.get("game", []), substitutions)
    else:
        # Legacy versions (pre-1.13): single space-delimited argument string
        legacy = version_info.get("minecraftArguments", "")
        for part in legacy.split(" "):
            cmd.append(_substitute(part, substitutions))

    return cmd


def _resolve_arg_list(entries: list, substitutions: dict) -> list[str]:
    out = []
    for entry in entries:
        if isinstance(entry, str):
            out.append(_substitute(entry, substitutions))
        else:
            # conditional entry: {"rules": [...], "value": "str-or-list"}
            if not rules_allow(entry.get("rules")):
                continue
            value = entry["value"]
            if isinstance(value, list):
                out.extend(_substitute(v, substitutions) for v in value)
            else:
                out.append(_substitute(value, substitutions))
    return out


def _substitute(s: str, subs: dict) -> str:
    for key, val in subs.items():
        s = s.replace("${" + key + "}", str(val))
    return s

def get_shared_cache_dir() -> Path:
    """Where version-specific but modpack-agnostic files (libraries, assets,
    client jars, natives) get cached ONCE and reused across every instance —
    instead of every instance keeping its own multi-GB copy of plain vanilla
    Minecraft data. This is the same approach Prism/MultiMC/the CurseForge
    app use; only mods/config/saves/etc. stay instance-specific."""
    if get_os_name() == "windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".local" / "share"
    return base / "MCLauncher" / "shared"


# ---------------------------------------------------------------------------
# Crash watching — the GUI sets game_exit_callback; every launch path (vanilla,
# Fabric/Quilt, Forge/NeoForge) ends in prepare_and_launch below, so one hook
# here covers all of them.
# ---------------------------------------------------------------------------

game_exit_callback = None  # callable(info: dict), called from a background thread


def _tail_lines(path: Path, n: int) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()[-n:]
    except OSError:
        return []


def _newest_since(folder: Path, pattern: str, since: float) -> Path | None:
    try:
        files = [p for p in folder.glob(pattern) if p.stat().st_mtime >= since]
    except OSError:
        return None
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _key_lines(lines: list[str], limit: int = 7) -> list[str]:
    """The part of a log that explains the crash: starting at the LAST error line
    (earlier errors are often harmless noise that Minecraft carried on past), keep
    it plus what follows, minus Java stack frames. Empty list if there's no error line."""
    last = next((i for i in range(len(lines) - 1, -1, -1)
                 if "/ERROR]" in lines[i] or "/FATAL]" in lines[i]), None)
    if last is None:
        return []
    out = []
    for line in lines[last:]:
        if line.lstrip().startswith("at ") or not line.strip():
            continue
        out.append(line.replace("\t", "    ")[:220])
        if len(out) >= limit:
            break
    return out


def _watch_game(proc, mc_dir: Path, version_id: str, started: float):
    """Waits for the game to exit. A clean exit (code 0) is ignored; anything else
    reports what Minecraft left behind. latest.log only counts if it was written
    during THIS run — otherwise it's an old log and would point at the wrong problem."""
    code = proc.wait()
    cb = game_exit_callback
    if cb is None or code == 0:
        return
    log_path = mc_dir / "logs" / "latest.log"
    fresh = log_path.is_file() and log_path.stat().st_mtime >= started - 1
    crash = _newest_since(mc_dir / "crash-reports", "crash-*.txt", started - 1)
    hs_err = _newest_since(mc_dir, "hs_err_pid*.log", started - 1)
    info = {
        "exit_code": code,
        "seconds": int(time.time() - started),
        "version_id": version_id,
        "mc_dir": str(mc_dir),
        "log_dir": str(log_path.parent if log_path.parent.is_dir() else mc_dir),
        "log_fresh": fresh,
        "tail": _tail_lines(log_path, 300) if fresh else [],
        "highlights": [],
        "crash_report": str(crash) if crash else None,
        "hs_err": str(hs_err) if hs_err else None,
    }
    info["highlights"] = _key_lines(info["tail"])
    try:
        cb(info)
    except Exception as e:
        print(f"[core] crash callback failed: {e}")


def _as_version_jar(jar: Path, versions_dir: Path, vid: str) -> Path:
    """Forge/NeoForge start with -DignoreList=...,<version_name>.jar: the bootstrap
    launcher skips any class-path jar with that exact file name when it builds its
    module layer. The installer's patched jar is called e.g. neoforge-21.1.250-client.jar
    instead, so it was NOT skipped and Java named a second module "neoforge" after it
    ("Module X reads more than one module named neoforge"). Same file, expected name:
    hard-linked (or copied) to versions/<id>/<id>.jar, where vanilla's jar already lives."""
    target = versions_dir / vid / f"{vid}.jar"
    if jar.name == target.name:
        return jar
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            same = target.stat().st_size == jar.stat().st_size and target.stat().st_mtime >= jar.stat().st_mtime
            if same:
                return target
            target.unlink()
        try:
            os.link(jar, target)
        except OSError:
            shutil.copy2(jar, target)
    except OSError as e:
        print(f"[core] couldn't prepare {target.name} ({e}); using {jar.name} as-is")
        return jar
    return target


# ---------------------------------------------------------------------------
# High-level: prepare + launch vanilla
# ---------------------------------------------------------------------------

def prepare_and_launch(
    instance_root: Path,
    version_id: str,
    auth: dict,
    memory_mb: int = 4096,
    extra_jvm_args: list[str] | None = None,
    version_info: dict | None = None,
    java_path: str | None = None,
    client_jar_override: Path | None = None,
):
    """Core entry point: downloads whatever's missing, launches Minecraft with
    the given auth dict (offline_auth(), elyby.authenticate(), or msauth's premium
    equivalent all produce a compatible dict).

    version_info: normally left as None, which looks the version up by id from
    Mojang's manifest (plain vanilla). Pass an already-built version_info dict
    instead for modded versions (e.g. loaders.install_fabric()'s merged
    profile) — those ids aren't real Mojang manifest entries, so they can't be
    looked up this way. version_id should match version_info['id'] in that case
    (used for the natives/versions cache folder name).

    client_jar_override: normally left as None (downloads vanilla's own client
    jar). Pass a path instead for Forge/NeoForge, whose actual bootable jar is
    the PATCHED output of the processor pipeline — a different file entirely
    from vanilla's client.jar."""
    instance_root = Path(instance_root).resolve()
    mc_dir = instance_root / "minecraft"
    shared = get_shared_cache_dir()
    versions_dir = shared / "versions"
    libs_dir = shared / "libraries"
    assets_dir = shared / "assets"
    natives_dir = shared / "natives" / version_id

    if version_info is None:
        print(f"[core] fetching version info for {version_id}...")
        version_info = get_version_info(version_id)

    if java_path is None:
        java_path = java_finder.resolve_java_path(version_info)

    print("[core] downloading libraries + natives...")
    classpath = ensure_libraries(version_info, libs_dir, natives_dir)

    if client_jar_override is not None:
        client_jar = _as_version_jar(Path(client_jar_override), versions_dir, version_info.get("id", version_id))
    else:
        print("[core] downloading client jar...")
        client_jar = ensure_client_jar(version_info, versions_dir)

    print("[core] downloading assets (first run can be slow)...")
    assets_index_id = ensure_assets(version_info, assets_dir)

    cmd = build_launch_command(
        instance_root, version_info, classpath, client_jar, natives_dir,
        assets_dir, assets_index_id, auth, memory_mb=memory_mb,
        extra_jvm_args=extra_jvm_args, java_path=java_path, libs_dir=libs_dir,
    )

    mc_dir.mkdir(parents=True, exist_ok=True)
    print(f"[core] launching {version_id} as {auth['username']} ({auth['user_type']})...")
    started = time.time()
    proc = subprocess.Popen(cmd, cwd=str(mc_dir))
    threading.Thread(target=_watch_game, args=(proc, mc_dir, version_id, started), daemon=True).start()
    return proc


def launch_vanilla(instance_root: Path, version_id: str, username: str, memory_mb: int = 4096):
    """Convenience wrapper: plain offline auth, no skin."""
    prepare_and_launch(instance_root, version_id, offline_auth(username), memory_mb=memory_mb)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: py core.py <version_id> <username> [instance_dir]")
        sys.exit(1)
    version = sys.argv[1]
    user = sys.argv[2]
    root = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("./test_instance")
    launch_vanilla(root, version, user)
