"""
mc_launcher.backfill_manifest — writes pack_manifest.json for an instance
created before packs.py started saving one, so it can go through
export_packwiz.py like anything imported after that change.

Two paths, in order of accuracy:

1. Packwiz-sourced instances: instances.json still has the original
   pack.toml URL (Instance.pack_source['url']) — just re-fetch and re-parse
   it. Gets back the exact original URLs/hashes, no guessing, no re-download
   of the actual mod jars.

2. Everything else (CurseForge/Modrinth-sourced, or no pack_source at all):
   there's no stored URL to re-fetch, so this fingerprints every jar under
   minecraft/ and asks CurseForge + Modrinth "do you recognize this file?" —
   sha1 lookup against Modrinth's /version_files, murmur2 fingerprint lookup
   against CurseForge's /fingerprints (CurseForge's own algorithm: strip
   whitespace bytes 9/10/13/32, then MurmurHash2 32-bit seed=1 — verified
   here against a known third-party test vector, not just assumed correct).

Files neither service recognizes end up in the manifest with url=None.
export_packwiz.py already treats a manifest entry with no `url` as "embed
directly" instead of writing a metafile, so nothing gets silently dropped —
it just isn't a thin/URL-based export for that one file.

Like curseforge.py, the CurseForge half of this hasn't been run against the
live API yet (sandbox has no network) — built from the documented endpoint
shape and the algorithm above. Worth reporting back what happens on the
first real attempt, same as curseforge.py.
"""
import hashlib
import json
import struct
import urllib.error
import urllib.request
from pathlib import Path

import export_packwiz  # shares its DEFAULT_EXCLUDE_DIRS so fingerprinting and export agree
import instances
import packs

MODRINTH_VERSION_FILES_URL = "https://api.modrinth.com/v2/version_files"
CURSEFORGE_FINGERPRINTS_URL = "https://api.curseforge.com/v1/fingerprints"
HASH_ALGO_SHA1 = 1  # CurseForge's own enum for hash algorithm, same as curseforge.py


class BackfillError(Exception):
    pass


# ---------------------------------------------------------------------------
# Path 1: packwiz — exact, re-fetches the original pack.toml
# ---------------------------------------------------------------------------

def backfill_from_packwiz(instance_root: Path, pack_toml_url: str) -> Path:
    import packwiz
    resolved = packwiz.parse_packwiz(pack_toml_url)
    mc_dir = Path(instance_root) / "minecraft"

    present = [f for f in resolved.files if (mc_dir / f.path).exists()]
    missing = [f.path for f in resolved.files if f not in present]
    if missing:
        print(f"[backfill] {len(missing)} file(s) in the pack.toml aren't on disk "
              f"(removed locally since install?), leaving them out: {missing}")
    resolved.files = present
    return packs.write_manifest(resolved, instance_root)


# ---------------------------------------------------------------------------
# Path 2: fingerprinting — best-effort, only for files the APIs recognize
# ---------------------------------------------------------------------------

def _murmur2_32(data: bytes, seed: int) -> int:
    """Austin Appleby's MurmurHash2 (32-bit). Verified against a known
    third-party test vector: murmur2_32(bytes([1,2,3,4]), seed=0) == 1487941662."""
    m, r, mask = 0x5bd1e995, 24, 0xFFFFFFFF
    length = len(data)
    h = (seed ^ length) & mask
    n_blocks = length // 4
    for i in range(n_blocks):
        k = struct.unpack_from("<I", data, i * 4)[0]
        k = (k * m) & mask
        k ^= k >> r
        k = (k * m) & mask
        h = (h * m) & mask
        h ^= k
    tail = data[n_blocks * 4:]
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


def curseforge_fingerprint(data: bytes) -> int:
    """CurseForge's own fingerprint: strip whitespace bytes, then murmur2 seed=1."""
    stripped = bytes(b for b in data if b not in (9, 10, 13, 32))
    return _murmur2_32(stripped, 1)


def _post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "Accept": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise BackfillError(f"{url} -> {e.code}: {e.read().decode('utf-8', 'ignore')}") from None


def _lookup_modrinth(sha1_list: list[str]) -> dict[str, dict]:
    """sha1 -> {'url', 'sha1', 'sha512'} for every hash Modrinth recognizes."""
    if not sha1_list:
        return {}
    resp = _post_json(MODRINTH_VERSION_FILES_URL, {"hashes": sha1_list, "algorithm": "sha1"})
    matches = {}
    for sha1, version in resp.items():
        vfiles = version.get("files", [])
        file_entry = next((f for f in vfiles if f.get("hashes", {}).get("sha1") == sha1),
                           vfiles[0] if vfiles else None)
        if file_entry:
            matches[sha1] = {"url": file_entry["url"], "sha1": sha1,
                              "sha512": file_entry.get("hashes", {}).get("sha512")}
    return matches


def _lookup_curseforge(fingerprints: list[int], api_key: str) -> dict[int, dict]:
    """fingerprint -> {'url', 'sha1', 'project_id', 'file_id'} for every fingerprint
    CurseForge recognizes."""
    if not fingerprints:
        return {}
    resp = _post_json(CURSEFORGE_FINGERPRINTS_URL, {"fingerprints": fingerprints},
                       headers={"x-api-key": api_key})
    matches = {}
    for m in resp.get("data", {}).get("exactMatches", []):
        f = m["file"]
        sha1 = next((h["value"] for h in f.get("hashes", []) if h.get("algo") == HASH_ALGO_SHA1), None)
        matches[m["id"]] = {"url": f.get("downloadUrl"), "sha1": sha1,
                             "project_id": f.get("modId"), "file_id": f.get("id")}
    return matches


def _is_excluded(rel: Path) -> bool:
    """Same rule export_packwiz.py uses for its direct-embed pass — instance
    state (saves/, screenshots/, ...) and any dot-dir. Dot-dirs matter most
    here: Fabric Loader caches locally-transformed copies of every mod under
    .fabric/processedMods/ (and a remapped client jar under
    .fabric/remappedJars/) — those aren't the original downloaded files, so
    fingerprinting them is wasted API calls that will never match anything
    and were never going to be exported anyway."""
    return rel.parts[0] in export_packwiz.DEFAULT_EXCLUDE_DIRS or \
        any(p.startswith(".") for p in rel.parts)


def backfill_by_fingerprint(instance_root: Path, minecraft_version: str, loader: str | None,
                             loader_version: str | None, name: str | None = None,
                             curseforge_api_key: str | None = None) -> Path:
    mc_dir = Path(instance_root) / "minecraft"
    jar_paths = [p for p in mc_dir.rglob("*.jar")
                 if p.is_file() and not _is_excluded(p.relative_to(mc_dir))]
    if not jar_paths:
        raise BackfillError(f"No .jar files found under {mc_dir}")

    data_by_path = {p: p.read_bytes() for p in jar_paths}
    sha1_by_path = {p: hashlib.sha1(d).hexdigest() for p, d in data_by_path.items()}
    fp_by_path = {p: curseforge_fingerprint(d) for p, d in data_by_path.items()}

    modrinth_matches = _lookup_modrinth(list(sha1_by_path.values()))
    curseforge_matches = {}
    if curseforge_api_key:
        curseforge_matches = _lookup_curseforge(list(fp_by_path.values()), curseforge_api_key)
    else:
        print("[backfill] no CurseForge API key given — skipping CurseForge lookup, "
              "Modrinth-recognized files only")

    files, unresolved = [], []
    for p in jar_paths:
        rel = str(p.relative_to(mc_dir))
        sha1 = sha1_by_path[p]
        mr = modrinth_matches.get(sha1)
        cf = curseforge_matches.get(fp_by_path[p])
        if mr:
            files.append(packs.ResolvedFile(path=rel, url=mr["url"], sha1=sha1,
                                             sha256=hashlib.sha256(data_by_path[p]).hexdigest()))
        elif cf:
            files.append(packs.ResolvedFile(path=rel, url=cf["url"], sha1=cf.get("sha1") or sha1,
                                             curseforge_project_id=cf.get("project_id"),
                                             curseforge_file_id=cf.get("file_id")))
        else:
            unresolved.append(rel)
            files.append(packs.ResolvedFile(path=rel, url=None,
                                             sha256=hashlib.sha256(data_by_path[p]).hexdigest()))

    if unresolved:
        print(f"[backfill] {len(unresolved)}/{len(jar_paths)} file(s) not recognized by "
              f"either service — these embed directly on export instead of using a source "
              f"URL: {unresolved}")

    resolved = packs.ResolvedPack(name=name or Path(instance_root).name,
                                   minecraft_version=minecraft_version, loader=loader,
                                   loader_version=loader_version, files=files)
    return packs.write_manifest(resolved, instance_root)


# ---------------------------------------------------------------------------
# Entry point: picks the right path automatically for a registered instance
# ---------------------------------------------------------------------------

def backfill(instance_name: str, curseforge_api_key: str | None = None, force: bool = False) -> Path:
    inst = instances.get(instance_name)
    if not inst:
        raise BackfillError(f"No instance named '{instance_name}'")
    if packs.read_manifest(inst.path) and not force:
        raise BackfillError(f"'{instance_name}' already has a manifest — pass force=True "
                             f"(CLI: --force) to overwrite it")

    source = inst.pack_source or {}
    if source.get("type") == "packwiz" and source.get("url"):
        print(f"[backfill] '{instance_name}' is packwiz-sourced — re-fetching original pack.toml")
        return backfill_from_packwiz(inst.path, source["url"])

    print(f"[backfill] '{instance_name}' has no recoverable source URL — fingerprinting "
          f"jars under minecraft/ against CurseForge/Modrinth instead")
    return backfill_by_fingerprint(inst.path, inst.minecraft_version, inst.loader,
                                    inst.loader_version, name=instance_name,
                                    curseforge_api_key=curseforge_api_key)


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    force = "--force" in args
    if force:
        args.remove("--force")
    if len(args) < 1:
        print("usage: py backfill_manifest.py <instance_name> [curseforge_api_key] [--force]")
        sys.exit(1)
    api_key = args[1] if len(args) > 1 else None
    if not api_key:
        import settings
        api_key = settings.get_curseforge_api_key()
    result_path = backfill(args[0], curseforge_api_key=api_key, force=force)
    print(f"[backfill] wrote {result_path}")
