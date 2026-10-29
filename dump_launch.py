"""
dump_launch.py - shows the exact Java command the launcher WOULD run for an instance, without starting the game.

    py dump_launch.py "The Broken Script"

Prints only the parts that matter for the 'more than one module named neoforge' crash:
the module path (-p), the ignore list, and any neoforge/client jars on the class path.
"""
import subprocess as _real_subprocess
import sys

import core
import instances


class _Shim:
    """Stands in for the subprocess module inside core.py only: Popen records the command instead of running it."""
    captured = None

    def __getattr__(self, name):
        return getattr(_real_subprocess, name)

    def Popen(self, cmd, *a, **k):
        _Shim.captured = list(cmd)
        raise SystemExit("(captured - the game was NOT started)")


def show(cmd):
    print(f"\njava: {cmd[0]}")
    jvm, game, main = [], [], None
    for i, a in enumerate(cmd[1:], 1):
        if a == "cpw.mods.bootstraplauncher.BootstrapLauncher" or (main is None and not a.startswith("-") and "." in a and "/" not in a and "\\" not in a and not a.startswith("D")):
            main = a
    print("main class:", main)
    for i, a in enumerate(cmd):
        if a in ("-p", "--module-path") and i + 1 < len(cmd):
            print("\nMODULE PATH (-p):")
            for p in cmd[i + 1].replace(";", "\n").replace(":\\", ":\\").split("\n"):
                print("   ", p.split("libraries")[-1] if "libraries" in p else p)
        if a.startswith("-DignoreList="):
            print("\nIGNORE LIST:", a.split("=", 1)[1])
        if a.startswith("-DlegacyClassPath="):
            entries = [e for e in a.split("=", 1)[1].split(";") if e]
            print(f"\nLEGACY CLASSPATH: {len(entries)} entries; the neoforge/client ones:")
            for e in entries:
                if "neoforge" in e.lower() or "client" in e.lower():
                    print("   ", e)
    cp = [cmd[i + 1] for i, a in enumerate(cmd) if a in ("-cp", "-classpath") and i + 1 < len(cmd)]
    if cp:
        print("\n-cp neoforge/client entries:")
        for e in cp[0].split(";"):
            if "neoforge" in e.lower() or "client" in e.lower():
                print("   ", e)


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "The Broken Script"
    core.subprocess = _Shim()
    try:
        instances.launch(name, core.offline_auth("diag"))
    except SystemExit:
        pass
    if _Shim.captured is None:
        sys.exit("No launch command was built (see any error above).")
    show(_Shim.captured)


if __name__ == "__main__":
    main()
