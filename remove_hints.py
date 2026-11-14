"""
remove_hints.py - one-time script. Run from C:\\MCLauncher:   py remove_hints.py

What it does (nothing is changed unless ALL edits match exactly):
  1. core.py, gui.py : removes the "build metadata" import block
  2. voidbox.spec    : replaces the per-build tag loop with a generic private-includes reader
  3. build.ps1       : replaces the tag step with a generic private pre-build hook
  4. creates private_prebuild.ps1 + private_includes.txt (only if canary.py exists)
     and adds both to .git\\info\\exclude
Backups: <file>.bak next to each changed file. Works with LF and CRLF files.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

BLOCK_RE = re.compile(
    r"# --- build metadata ---\n"
    r"try:\n"
    r"    from _canary import BUILD_TAG\n"
    r"except ImportError:\n"
    r"    BUILD_TAG = None\n"
    r"# --- end build metadata ---\n+"
)

SPEC_OLD = (
    "# Optional per-build tag module\n"
    "for _m in (\"_canary\",):\n"
    "    if os.path.exists(os.path.join(HERE, _m + \".py\")):\n"
    "        hiddenimports += [_m]\n"
)
SPEC_NEW = (
    "# Optional private extras: modules listed in private_includes.txt (not in git) are bundled too.\n"
    "_extras = os.path.join(HERE, \"private_includes.txt\")\n"
    "if os.path.exists(_extras):\n"
    "    with open(_extras, encoding=\"utf-8\") as _f:\n"
    "        hiddenimports += [_l.strip() for _l in _f if _l.strip()]\n"
)

PS_OLD = (
    "# Per-version build tag.\n"
    "if (Test-Path canary.py) {\n"
    "    py canary.py ensure $Version\n"
    "    if ($LASTEXITCODE -ne 0) { throw \"canary.py failed\" }\n"
    "}\n"
)
PS_NEW = (
    "# Optional private pre-build step (not in git).\n"
    "if (Test-Path private_prebuild.ps1) { & .\\private_prebuild.ps1 $Version }\n"
)

PRIVATE_PS = (
    "param($Version)\n"
    "if (Test-Path canary.py) {\n"
    "    py canary.py ensure $Version\n"
    "    if ($LASTEXITCODE -ne 0) { throw \"canary.py failed\" }\n"
    "}\n"
    "if (Test-Path _canary.py) { Set-Content private_includes.txt \"_canary\" -Encoding ascii }\n"
)


def read(path):
    with open(path, "rb") as f:
        raw = f.read()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")
    return text, crlf


def write(path, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def plan():
    edits = []  # (path, new_text, crlf)
    problems = []

    for name in ("core.py", "gui.py"):
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            problems.append(f"{name}: not found")
            continue
        text, crlf = read(p)
        if len(BLOCK_RE.findall(text)) != 1:
            problems.append(f"{name}: build metadata block not found exactly once (already patched, or the file differs)")
            continue
        edits.append((p, BLOCK_RE.sub("", text, count=1), crlf))

    for name, old, new, label in (
        ("voidbox.spec", SPEC_OLD, SPEC_NEW, "per-build tag loop"),
        ("build.ps1", PS_OLD, PS_NEW, "tag step"),
    ):
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            problems.append(f"{name}: not found")
            continue
        text, crlf = read(p)
        if text.count(old) != 1:
            problems.append(f"{name}: {label} not found exactly once (already patched, or the file differs)")
            continue
        edits.append((p, text.replace(old, new, 1), crlf))
    return edits, problems


def main():
    edits, problems = plan()
    if problems:
        print("NOTHING CHANGED. Problems:")
        for pr in problems:
            print("  -", pr)
        sys.exit(1)

    for p, new_text, crlf in edits:
        with open(p, "rb") as f:
            orig = f.read()
        with open(p + ".bak", "wb") as f:
            f.write(orig)
        write(p, new_text, crlf)
        print("patched", os.path.basename(p))

    if os.path.exists(os.path.join(HERE, "canary.py")):
        with open(os.path.join(HERE, "private_prebuild.ps1"), "w", encoding="ascii", newline="\r\n") as f:
            f.write(PRIVATE_PS)
        if os.path.exists(os.path.join(HERE, "_canary.py")):
            with open(os.path.join(HERE, "private_includes.txt"), "w", encoding="ascii") as f:
                f.write("_canary\n")
        print("created private_prebuild.ps1 and private_includes.txt")
    else:
        print("NOTE: canary.py not found here, so no private files were created")

    exclude = os.path.join(HERE, ".git", "info", "exclude")
    if os.path.exists(exclude):
        with open(exclude, "r", encoding="utf-8", errors="replace") as f:
            have = f.read()
        add = [n for n in ("private_prebuild.ps1", "private_includes.txt") if n not in have]
        if add:
            with open(exclude, "a", encoding="utf-8") as f:
                if have and not have.endswith("\n"):
                    f.write("\n")
                f.write("\n".join(add) + "\n")
            print("added to .git/info/exclude:", ", ".join(add))
    else:
        print("WARNING: .git/info/exclude not found - add private_prebuild.ps1 and private_includes.txt to it by hand")

    print("\nDone. Next: py -m py_compile core.py gui.py   then build as usual.")


if __name__ == "__main__":
    main()
