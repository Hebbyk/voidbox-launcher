"""
search_pagination.py - one-time script. Run from C:\\MCLauncher:   py search_pagination.py

Adds an offset parameter to every search function in search.py, so results can be
fetched a page at a time instead of only ever the first batch. Parameter names match
each API's own docs: Modrinth's search takes "offset" (skips that many results, verified
against docs.modrinth.com); CurseForge's /mods/search takes "index", a zero-based item
offset (verified against CurseForge's own OpenAPI spec at api.curseforge.com/swagger).

Only search.py is touched. Nothing is changed unless all 6 edits match exactly.
Backup: search.py.bak. LF and CRLF both fine.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

EDITS = [
    ('def search_modrinth(query: str, limit: int = 20) -> list[dict]:\n'
     '    params = {"query": query, "facets": json.dumps([["project_type:modpack"]]),\n'
     '              "limit": str(limit)}\n',
     'def search_modrinth(query: str, limit: int = 20, offset: int = 0) -> list[dict]:\n'
     '    params = {"query": query, "facets": json.dumps([["project_type:modpack"]]),\n'
     '              "limit": str(limit), "offset": str(offset)}\n'),

    ('def search_curseforge(query: str, api_key: str, limit: int = 20) -> list[dict]:\n'
     '    params = {"gameId": CURSEFORGE_GAME_ID, "classId": CURSEFORGE_MODPACK_CLASS_ID,\n'
     '              "searchFilter": query, "pageSize": limit, "sortField": 2}\n',
     'def search_curseforge(query: str, api_key: str, limit: int = 20, offset: int = 0) -> list[dict]:\n'
     '    params = {"gameId": CURSEFORGE_GAME_ID, "classId": CURSEFORGE_MODPACK_CLASS_ID,\n'
     '              "searchFilter": query, "pageSize": limit, "index": offset, "sortField": 2}\n'),

    ('def search_modrinth_mods(query: str, limit: int = 20) -> list[dict]:\n'
     '    """Same shape as search_modrinth() but for individual mods, not packs —\n'
     '    needed for adding a single mod to an already-installed instance."""\n'
     '    params = {"query": query, "facets": json.dumps([["project_type:mod"]]),\n'
     '              "limit": str(limit)}\n',
     'def search_modrinth_mods(query: str, limit: int = 20, offset: int = 0) -> list[dict]:\n'
     '    """Same shape as search_modrinth() but for individual mods, not packs —\n'
     '    needed for adding a single mod to an already-installed instance."""\n'
     '    params = {"query": query, "facets": json.dumps([["project_type:mod"]]),\n'
     '              "limit": str(limit), "offset": str(offset)}\n'),

    ('def search_curseforge_mods(query: str, api_key: str, limit: int = 20) -> list[dict]:\n'
     '    """Same shape as search_curseforge() but for individual mods."""\n'
     '    params = {"gameId": CURSEFORGE_GAME_ID, "classId": CURSEFORGE_MOD_CLASS_ID,\n'
     '              "searchFilter": query, "pageSize": limit, "sortField": 2}\n',
     'def search_curseforge_mods(query: str, api_key: str, limit: int = 20, offset: int = 0) -> list[dict]:\n'
     '    """Same shape as search_curseforge() but for individual mods."""\n'
     '    params = {"gameId": CURSEFORGE_GAME_ID, "classId": CURSEFORGE_MOD_CLASS_ID,\n'
     '              "searchFilter": query, "pageSize": limit, "index": offset, "sortField": 2}\n'),

    ('def search_all_mods(query: str, curseforge_api_key: str | None = None, limit: int = 10) -> list[dict]:\n'
     '    """Mods version of search_all() — used when adding to an existing\n'
     '    instance instead of creating a new one from a modpack."""\n'
     '    results = search_modrinth_mods(query, limit)\n'
     '    if curseforge_api_key:\n'
     '        try:\n'
     '            results += search_curseforge_mods(query, curseforge_api_key, limit)\n'
     '        except SearchError as e:\n'
     '            print(f"[search] CurseForge mod search failed, showing Modrinth results only: {e}")\n'
     '    return results\n',
     'def search_all_mods(query: str, curseforge_api_key: str | None = None, limit: int = 10,\n'
     '                     offset: int = 0) -> list[dict]:\n'
     '    """Mods version of search_all() — used when adding to an existing\n'
     '    instance instead of creating a new one from a modpack."""\n'
     '    results = search_modrinth_mods(query, limit, offset)\n'
     '    if curseforge_api_key:\n'
     '        try:\n'
     '            results += search_curseforge_mods(query, curseforge_api_key, limit, offset)\n'
     '        except SearchError as e:\n'
     '            print(f"[search] CurseForge mod search failed, showing Modrinth results only: {e}")\n'
     '    return results\n'),

    ('def search_all(query: str, curseforge_api_key: str | None = None, limit: int = 10) -> list[dict]:\n'
     '    """Searches both sources at once (skips CurseForge if no key given, rather\n'
     '    than failing the whole search over a missing optional key)."""\n'
     '    results = search_modrinth(query, limit)\n'
     '    if curseforge_api_key:\n'
     '        try:\n'
     '            results += search_curseforge(query, curseforge_api_key, limit)\n'
     '        except SearchError as e:\n'
     '            print(f"[search] CurseForge search failed, showing Modrinth results only: {e}")\n'
     '    return results\n',
     'def search_all(query: str, curseforge_api_key: str | None = None, limit: int = 10,\n'
     '                offset: int = 0) -> list[dict]:\n'
     '    """Searches both sources at once (skips CurseForge if no key given, rather\n'
     '    than failing the whole search over a missing optional key)."""\n'
     '    results = search_modrinth(query, limit, offset)\n'
     '    if curseforge_api_key:\n'
     '        try:\n'
     '            results += search_curseforge(query, curseforge_api_key, limit, offset)\n'
     '        except SearchError as e:\n'
     '            print(f"[search] CurseForge search failed, showing Modrinth results only: {e}")\n'
     '    return results\n'),
]


def main():
    p = os.path.join(HERE, "search.py")
    if not os.path.exists(p):
        print("NOTHING CHANGED. search.py not found."); sys.exit(1)
    with open(p, "rb") as f:
        raw = f.read()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")

    problems = []
    for old, new, in [(o, n) for o, n in EDITS]:
        if text.count(old) != 1:
            problems.append(f"found {text.count(old)} match(es), expected 1, for:\n    {old.strip().splitlines()[0]}")
    if problems:
        print("NOTHING CHANGED. Problems:")
        for pr in problems:
            print("  -", pr)
        sys.exit(1)

    for old, new in EDITS:
        text = text.replace(old, new, 1)

    with open(p + ".bak", "wb") as f:
        f.write(raw)
    out = text.replace("\n", "\r\n") if crlf else text
    with open(p, "wb") as f:
        f.write(out.encode("utf-8"))
    print("patched search.py: added offset support to all 6 search functions")
    print("\nDone. Next: py -m py_compile search.py   then run gui_pagination.py.")


if __name__ == "__main__":
    main()
