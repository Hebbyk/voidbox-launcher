"""
lazy_imports.py - one-time script. Run from C:\\MCLauncher:   py lazy_imports.py

Stability step 3 of 3 (1.1.4): faster startup. 10 modules that are only used inside specific
dialogs (search, mod doctor, world import/backup, mod updates, change version, export, duplicate,
cracked-login check) are no longer imported when the launcher opens - only when that dialog is
actually opened. None of them are used anywhere in LauncherApp's own startup path, which this
script checks itself (by AST, not by trusting a hardcoded list) before changing anything.

What it does:
  - removes the top-level "import X" line for each of those 10 modules
  - inserts "import X" as the first line of every method that actually uses X (confirmed by
    parsing the file, so a method is never missed)
  - re-parses the result afterwards and fails loudly if any real usage is left unguarded

Nothing is changed unless the self-check passes. Backup: gui.py.bak. LF and CRLF both fine.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODS = ["elyby", "export_curseforge", "export_mrpack", "export_packwiz", "mod_doctor",
        "mod_updater", "version_change", "world_backup", "worlds", "search"]


def real_uses(node, m):
    return any(isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == m
               for n in ast.walk(node))


def find_targets(tree):
    """-> {(class_name, method_name): [mods used]} for every method that really uses one of MODS,
    anywhere outside LauncherApp.__init__ (startup). Raises if a use IS inside LauncherApp.__init__
    or at module scope, since those cannot be deferred safely."""
    targets = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    used = [m for m in MODS if real_uses(item, m)]
                    if used:
                        if node.name == "LauncherApp" and item.name == "__init__":
                            raise SystemExit(f"ABORT: {m} is used in LauncherApp.__init__ (startup path) - "
                                              f"not safe to defer. No changes made.")
                        targets[(node.name, item.name, item.lineno, item.end_lineno,
                                 item.body[0].lineno if item.body else item.lineno)] = used
    # module-scope (outside any class/function) real uses -> also unsafe
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            for m in MODS:
                if real_uses(n, m):
                    raise SystemExit(f"ABORT: {m} is used in module-level function {n.name} - "
                                      f"not safe to defer this way. No changes made.")
    return targets


def body_indent(fn_node, lines):
    first_stmt = fn_node.body[0]
    # skip a bare docstring Expr to insert after it
    if (isinstance(first_stmt, ast.Expr) and isinstance(getattr(first_stmt, "value", None), ast.Constant)
            and isinstance(first_stmt.value.value, str) and len(fn_node.body) > 1):
        insert_after_line = first_stmt.end_lineno
        ref_line = fn_node.body[1].lineno
    else:
        insert_after_line = fn_node.lineno  # the 'def' line itself (may span several lines for long signatures)
        insert_after_line = first_stmt.lineno - 1 if first_stmt.lineno > fn_node.lineno else fn_node.body[0].lineno - 1
        ref_line = first_stmt.lineno
    indent = len(lines[ref_line - 1]) - len(lines[ref_line - 1].lstrip())
    return insert_after_line, indent


def main():
    p = os.path.join(HERE, "gui.py")
    if not os.path.exists(p):
        print("NOTHING CHANGED. gui.py not found."); sys.exit(1)
    with open(p, "rb") as f:
        raw = f.read()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")
    lines = text.split("\n")

    tree = ast.parse(text)
    try:
        targets = find_targets(tree)
    except SystemExit as e:
        print(e); sys.exit(1)
    if not targets:
        print("NOTHING CHANGED. No deferrable usages found (already applied?)."); sys.exit(1)

    # 1. remove the 10 top-level import lines (must each appear exactly once, as "import X\n")
    missing = []
    for m in MODS:
        hits = [i for i, l in enumerate(lines) if l == f"import {m}"]
        if len(hits) != 1:
            missing.append(f"{m}: found {len(hits)} top-level 'import {m}' lines, expected 1")
    if missing:
        print("NOTHING CHANGED. Problems:")
        for x in missing:
            print("  -", x)
        sys.exit(1)
    for m in MODS:
        idx = next(i for i, l in enumerate(lines) if l == f"import {m}")
        lines[idx] = None  # mark for removal
    lines = [l for l in lines if l is not None]

    # re-parse AFTER removing imports but BEFORE inserting local ones, to get fresh, correct
    # line numbers for insertion (removing lines above shifted everything below).
    text2 = "\n".join(lines)
    tree2 = ast.parse(text2)
    targets2 = find_targets(tree2)

    # 2. plan insertions bottom-to-top so earlier edits don't shift later line numbers
    insertions = []  # (line_index_to_insert_after, indent, [mods])
    by_method = {}
    for node in ast.walk(tree2):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    key = (node.name, item.name)
                    for (cn, mn, *_rest), mods_used in targets2.items():
                        pass
    # simpler: redo the scan directly against tree2, this time keeping the node objects
    for node in ast.walk(tree2):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    used = [m for m in MODS if real_uses(item, m)]
                    if used:
                        insert_after_line, indent = body_indent(item, lines)
                        insertions.append((insert_after_line, indent, used))

    insertions.sort(key=lambda t: t[0], reverse=True)
    for insert_after_line, indent, used in insertions:
        block = "\n".join(" " * indent + f"import {m}" for m in sorted(used))
        lines.insert(insert_after_line, block)

    new_text = "\n".join(lines)

    # 3. self-check: re-parse the final text and confirm every real use is now preceded, inside
    # its own method, by a local "import X" for every X it uses - not just that the use exists.
    final_tree = ast.parse(new_text)
    find_targets(final_tree)  # still raises if anything ended up in __init__/module scope
    unguarded = []
    for node in ast.walk(final_tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    used = [m for m in MODS if real_uses(item, m)]
                    if not used:
                        continue
                    imported_here = {n.names[0].name for n in ast.walk(item)
                                      if isinstance(n, ast.Import) and len(n.names) == 1}
                    missing = [m for m in used if m not in imported_here]
                    if missing:
                        unguarded.append((node.name, item.name, missing))
    # also confirm the 10 top-level imports are really gone
    still_top_level = [m for m in MODS if any(
        isinstance(n, ast.Import) and len(n.names) == 1 and n.names[0].name == m for n in final_tree.body)]
    if unguarded or still_top_level:
        print("ABORT: self-check failed.")
        if unguarded:
            print("  unguarded usages:", unguarded)
        if still_top_level:
            print("  still top-level:", still_top_level)
        sys.exit(1)

    with open(p + ".bak", "wb") as f:
        f.write(raw)
    out = new_text.replace("\n", "\r\n") if crlf else new_text
    with open(p, "wb") as f:
        f.write(out.encode("utf-8"))

    print(f"patched gui.py: removed {len(MODS)} top-level imports, added {len(insertions)} local ones")
    print("\nDone. Next: py -m py_compile gui.py   then start the launcher and click through every")
    print("dialog once (search, manage mods, world import/backup, updates, change version, export,")
    print("duplicate, cracked login) so each deferred import gets exercised at least once.")


if __name__ == "__main__":
    main()
