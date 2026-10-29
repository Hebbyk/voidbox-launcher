"""
mc_launcher.curseforge — imports a CurseForge modpack .zip.

Needs a free CurseForge API key from https://console.curseforge.com (self-serve
signup, no approval wait, unlike the Microsoft situation) — manifest.json only
has {projectID, fileID} pairs, not actual download URLs, so the API is the only
way to resolve those into something downloadable.

NOT independently tested against the live API (api.curseforge.com isn't
reachable from the sandbox this was built in) — built carefully from the
documented v1 schema and several reference implementations, but this is the
one importer of the three that hasn't been run for real yet. Worth reporting
back what happens on the first real attempt.

Known real limitation, not a bug: some mod authors disable third-party
downloads entirely. For those, there's no API-based way to get the file at
all — you'd need to download it manually from the CurseForge website and
drop it into the instance's mods/ folder yourself.
"""
import json
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from packs import ResolvedFile, ResolvedPack

API_BASE = "https://api.curseforge.com/v1"
HASH_ALGO_SHA1 = 1  # CurseForge's own enum for hash algorithm in file metadata


class CurseForgeError(Exception):
    pass


def _api_request(path: str, api_key: str, payload: dict | None = None) -> dict:
    url = f"{API_BASE}{path}"
    headers = {"x-api-key": api_key, "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    else:
        req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise CurseForgeError(f"CurseForge API error {e.code}: {body}") from None


def _fallback_cdn_url(file_id: int, filename: str) -> str:
    """Raw CDN path, keyed off the file ID — works for some files whose API
    'downloadUrl' comes back null due to author restrictions, but not all of
    them; some authors block this route too, and then there's no automatic
    way to fetch that particular mod."""
    a, b = file_id // 1000, file_id % 1000
    return f"https://mediafiles.forgecdn.net/files/{a}/{b}/{urllib.parse.quote(filename)}"


def parse_curseforge_zip(zip_path: str, api_key: str) -> ResolvedPack:
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        overrides_name = manifest.get("overrides", "overrides")

        extract_dir = Path(tempfile.mkdtemp(prefix="cfpack_"))
        for name in zf.namelist():
            if name.startswith(overrides_name + "/"):
                zf.extract(name, extract_dir)

    overrides_dir = extract_dir / overrides_name
    if not overrides_dir.exists():
        overrides_dir = None

    mc = manifest.get("minecraft", {})
    loader, loader_version = None, None
    for entry in mc.get("modLoaders", []):
        loader_id = entry.get("id", "")
        if "-" in loader_id:
            loader, loader_version = loader_id.split("-", 1)
            if entry.get("primary"):
                break

    file_refs = manifest.get("files", [])
    file_ids = [f["fileID"] for f in file_refs]

    # Resolve in one batch call per 50 files rather than one call per mod
    file_by_id = {}
    for i in range(0, len(file_ids), 50):
        chunk = file_ids[i:i + 50]
        resp = _api_request("/mods/files", api_key, {"fileIds": chunk})
        for f in resp.get("data", []):
            file_by_id[f["id"]] = f

    files = []
    unresolved = []
    for ref in file_refs:
        fid = ref["fileID"]
        meta = file_by_id.get(fid)
        if not meta:
            unresolved.append(fid)
            continue

        url = meta.get("downloadUrl") or _fallback_cdn_url(fid, meta["fileName"])
        sha1 = next((h["value"] for h in meta.get("hashes", [])
                     if h.get("algo") == HASH_ALGO_SHA1), None)

        files.append(ResolvedFile(
            path=f"mods/{meta['fileName']}",
            url=url,
            sha1=sha1,
            size=meta.get("fileLength"),
            curseforge_project_id=meta.get("modId"),
            curseforge_file_id=fid,
        ))

    if unresolved:
        print(f"[curseforge] {len(unresolved)} file(s) the API wouldn't resolve at all "
              f"(IDs: {unresolved}) — likely author-restricted, needs manual download.")

    return ResolvedPack(
        name=manifest.get("name", zip_path.stem),
        minecraft_version=mc.get("version"),
        loader=loader,
        loader_version=loader_version,
        files=files,
        overrides_dir=overrides_dir,
    )


if __name__ == "__main__":
    import sys
    from packs import install_pack
    if len(sys.argv) < 4:
        print("usage: py curseforge.py <pack.zip> <instance_dir> <api_key>")
        sys.exit(1)
    resolved = parse_curseforge_zip(sys.argv[1], sys.argv[3])
    install_pack(resolved, Path(sys.argv[2]))
