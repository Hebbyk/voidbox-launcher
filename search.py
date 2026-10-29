"""
mc_launcher.search — search CurseForge and Modrinth for modpacks, then
download whichever version the user picks. The downloaded file feeds
straight into the SAME importers already built and tested
(curseforge.parse_curseforge_zip / modrinth.parse_mrpack) — search is just
a way to find the pack file, not a separate import path.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import core

MODRINTH_API = "https://api.modrinth.com/v2"
CURSEFORGE_API = "https://api.curseforge.com/v1"
CURSEFORGE_GAME_ID = 432
CURSEFORGE_MODPACK_CLASS_ID = 4471
CURSEFORGE_MOD_CLASS_ID = 6  # verified against CurseForge's own API docs/known wrappers, not assumed


class SearchError(Exception):
    pass


def _fetch_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise SearchError(f"Search request failed ({e.code}): {url}") from None


# ---------------------------------------------------------------------------
# Searching
# ---------------------------------------------------------------------------

def search_modrinth(query: str, limit: int = 20) -> list[dict]:
    params = {"query": query, "facets": json.dumps([["project_type:modpack"]]),
              "limit": str(limit)}
    url = f"{MODRINTH_API}/search?{urllib.parse.urlencode(params)}"
    resp = _fetch_json(url)
    return [{
        "source": "modrinth",
        "id": hit["project_id"],
        "slug": hit["slug"],
        "title": hit["title"],
        "description": hit.get("description", ""),
        "icon_url": hit.get("icon_url"),
        "downloads": hit.get("downloads", 0),
    } for hit in resp.get("hits", [])]


def search_curseforge(query: str, api_key: str, limit: int = 20) -> list[dict]:
    params = {"gameId": CURSEFORGE_GAME_ID, "classId": CURSEFORGE_MODPACK_CLASS_ID,
              "searchFilter": query, "pageSize": limit, "sortField": 2}
    url = f"{CURSEFORGE_API}/mods/search?{urllib.parse.urlencode(params)}"
    resp = _fetch_json(url, headers={"x-api-key": api_key, "Accept": "application/json"})
    return [{
        "source": "curseforge",
        "id": mod["id"],
        "title": mod["name"],
        "description": mod.get("summary", ""),
        "icon_url": (mod.get("logo") or {}).get("thumbnailUrl"),
        "downloads": mod.get("downloadCount", 0),
    } for mod in resp.get("data", [])]


def search_modrinth_mods(query: str, limit: int = 20) -> list[dict]:
    """Same shape as search_modrinth() but for individual mods, not packs —
    needed for adding a single mod to an already-installed instance."""
    params = {"query": query, "facets": json.dumps([["project_type:mod"]]),
              "limit": str(limit)}
    url = f"{MODRINTH_API}/search?{urllib.parse.urlencode(params)}"
    resp = _fetch_json(url)
    return [{
        "source": "modrinth",
        "id": hit["project_id"],
        "slug": hit["slug"],
        "title": hit["title"],
        "description": hit.get("description", ""),
        "icon_url": hit.get("icon_url"),
        "downloads": hit.get("downloads", 0),
    } for hit in resp.get("hits", [])]


def search_curseforge_mods(query: str, api_key: str, limit: int = 20) -> list[dict]:
    """Same shape as search_curseforge() but for individual mods."""
    params = {"gameId": CURSEFORGE_GAME_ID, "classId": CURSEFORGE_MOD_CLASS_ID,
              "searchFilter": query, "pageSize": limit, "sortField": 2}
    url = f"{CURSEFORGE_API}/mods/search?{urllib.parse.urlencode(params)}"
    resp = _fetch_json(url, headers={"x-api-key": api_key, "Accept": "application/json"})
    return [{
        "source": "curseforge",
        "id": mod["id"],
        "title": mod["name"],
        "description": mod.get("summary", ""),
        "icon_url": (mod.get("logo") or {}).get("thumbnailUrl"),
        "downloads": mod.get("downloadCount", 0),
    } for mod in resp.get("data", [])]


def search_all_mods(query: str, curseforge_api_key: str | None = None, limit: int = 10) -> list[dict]:
    """Mods version of search_all() — used when adding to an existing
    instance instead of creating a new one from a modpack."""
    results = search_modrinth_mods(query, limit)
    if curseforge_api_key:
        try:
            results += search_curseforge_mods(query, curseforge_api_key, limit)
        except SearchError as e:
            print(f"[search] CurseForge mod search failed, showing Modrinth results only: {e}")
    return results


def search_all(query: str, curseforge_api_key: str | None = None, limit: int = 10) -> list[dict]:
    """Searches both sources at once (skips CurseForge if no key given, rather
    than failing the whole search over a missing optional key)."""
    results = search_modrinth(query, limit)
    if curseforge_api_key:
        try:
            results += search_curseforge(query, curseforge_api_key, limit)
        except SearchError as e:
            print(f"[search] CurseForge search failed, showing Modrinth results only: {e}")
    return results


# ---------------------------------------------------------------------------
# Listing versions/files for a chosen result, and downloading one
# ---------------------------------------------------------------------------

def get_modrinth_versions(project_id: str) -> list[dict]:
    resp = _fetch_json(f"{MODRINTH_API}/project/{project_id}/version")
    out = []
    for v in resp:
        files = v.get("files", [])
        primary = next((f for f in files if f.get("primary")), files[0] if files else None)
        if not primary:
            continue
        out.append({"id": v["id"], "name": v.get("name", v["id"]),
                     "game_versions": v.get("game_versions", []),
                     "loaders": v.get("loaders", []),
                     "url": primary["url"], "filename": primary["filename"],
                     "changelog": v.get("changelog"),
                     "sha1": (primary.get("hashes") or {}).get("sha1")})
    return out


_CURSEFORGE_LOADER_NAMES = {"forge", "fabric", "neoforge", "quilt"}


def get_curseforge_files(mod_id: int, api_key: str, limit: int = 20) -> list[dict]:
    """CurseForge doesn't have a separate loader field on a file — its
    gameVersions list mixes MC versions, loader names, and tags like
    'Client'/'Server' together, so the loader has to be picked out of it."""
    url = f"{CURSEFORGE_API}/mods/{mod_id}/files?pageSize={limit}"
    resp = _fetch_json(url, headers={"x-api-key": api_key, "Accept": "application/json"})
    out = []
    for f in resp.get("data", []):
        game_versions = f.get("gameVersions", [])
        loaders = [gv for gv in game_versions if gv.lower() in _CURSEFORGE_LOADER_NAMES]
        mc_versions = [gv for gv in game_versions if gv.lower() not in _CURSEFORGE_LOADER_NAMES
                       and gv.lower() not in ("client", "server")]
        sha1 = next((h["value"] for h in f.get("hashes", []) if h.get("algo") == 1), None)
        out.append({"id": f["id"], "name": f.get("displayName", str(f["id"])),
                     "game_versions": mc_versions, "loaders": loaders,
                     "url": f.get("downloadUrl"), "filename": f.get("fileName"), "sha1": sha1})
    return out


# ---------------------------------------------------------------------------
# Full project detail (for a detail view — search results only carry a
# short blurb, not the long description or categories)
# ---------------------------------------------------------------------------

def get_modrinth_project(project_id: str) -> dict:
    """Full project detail. 'body' is the long-form markdown description
    shown on the project's actual Modrinth page — search_modrinth() only
    ever returns the short 'description' blurb, not this."""
    return _fetch_json(f"{MODRINTH_API}/project/{project_id}")


def get_curseforge_mod(mod_id: int, api_key: str) -> dict:
    """Full mod detail (categories, stats, etc). Note: this does NOT
    include the full formatted page description — CurseForge serves that
    as raw HTML from a separate '/mods/{id}/description' endpoint, which
    isn't fetched here since this GUI has no HTML rendering engine to show
    it with; 'summary' below is the same short text search already returns."""
    resp = _fetch_json(f"{CURSEFORGE_API}/mods/{mod_id}",
                        headers={"x-api-key": api_key, "Accept": "application/json"})
    return resp.get("data", {})


def download_pack_file(url: str, filename: str, dest_dir: Path) -> Path:
    if not url:
        raise SearchError("This file has no direct download URL (the author disabled "
                           "third-party downloads for it) — nothing to fetch.")
    dest = Path(dest_dir) / filename
    core.download_file(url, dest)
    return dest


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: py search.py <query> [curseforge_api_key]")
        sys.exit(1)
    query = sys.argv[1]
    api_key = sys.argv[2] if len(sys.argv) > 2 else None

    results = search_all(query, api_key)
    for r in results:
        print(f"[{r['source']}] {r['title']} (id={r['id']}, downloads={r['downloads']})")
        if r["description"]:
            print(f"    {r['description'][:100]}")
