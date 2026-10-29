"""Voidbox Launcher - license tripwire.
Refuses to start if LICENSE or NOTICE next to the app is missing/altered.
Call check_license() at the very top of your main file."""
import sys, pathlib

def _base():
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys.executable).parent
    return pathlib.Path(__file__).parent

def check_license():
    b = _base()
    try:
        lic = (b / "LICENSE").read_text(errors="ignore")
        notice = (b / "NOTICE").read_text(errors="ignore")
        ok = ("GNU GENERAL PUBLIC LICENSE" in lic
              and "Copyright (c) 2026 Hebby" in notice)
    except OSError:
        ok = False
    if not ok:
        try:
            import tkinter.messagebox as mb
            mb.showerror("Voidbox Launcher",
                         "LICENSE or NOTICE is missing or modified.\n"
                         "Get the official release from GitHub.")
        except Exception:
            print("LICENSE or NOTICE is missing or modified.")
        sys.exit(1)
