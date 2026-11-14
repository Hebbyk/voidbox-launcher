"""
crash_log.py - one-time script. Run from C:\\MCLauncher:   py crash_log.py

Stability step 2 of 3 (1.1.4): every uncaught error is written to a log file you can ask users for.
  - creates crashlog.py
  - gui.py : imports it and installs the hooks at startup

Log file: %LOCALAPPDATA%\\MCLauncher\\logs\\launcher-errors.log   (one older copy kept as .old)
Catches errors on the main thread, in background threads and inside button/menu callbacks.
Each entry has the time, launcher version, Windows/Python version and the traceback, run through
log_sanitizer first (user name, paths, tokens, e-mails, IPs hidden), so it is safe to paste publicly.
Nothing is changed unless both edits match exactly. Backup: gui.py.bak. LF and CRLF both fine.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

CRASHLOG = '''"""
crashlog - writes every uncaught error to a log file so a bug report can include it.
Location: %LOCALAPPDATA%\\\\MCLauncher\\\\logs\\\\launcher-errors.log (one older copy is kept as .old).
Entries pass through log_sanitizer, so user names, paths, tokens, e-mails and IPs are hidden.
This module must never raise: a problem while logging is silently ignored.
"""
import os
import platform
import sys
import threading
import time
import traceback
from pathlib import Path

import log_sanitizer

MAX_BYTES = 512 * 1024
_version = ""


def log_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path.home() / ".local" / "share"
    return base / "MCLauncher" / "logs" / "launcher-errors.log"


def _write(kind, exc_type, exc, tb):
    try:
        head = (f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} | Voidbox Launcher {_version} | "
                f"{platform.platform()} | Python {platform.python_version()} | {kind} ===\\n")
        body = "".join(traceback.format_exception(exc_type, exc, tb))
        entry = log_sanitizer.sanitize(head + body) + "\\n"
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > MAX_BYTES:
            os.replace(p, p.with_name(p.name + ".old"))
        with open(p, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        pass


def _excepthook(exc_type, exc, tb):
    if not issubclass(exc_type, KeyboardInterrupt):
        _write("main thread", exc_type, exc, tb)
    try:
        sys.__excepthook__(exc_type, exc, tb)
    except Exception:
        pass


def _thread_hook(args):
    if args.exc_type is not SystemExit:
        name = args.thread.name if args.thread else "?"
        _write(f"thread {name}", args.exc_type, args.exc_value, args.exc_traceback)
    try:
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    except Exception:
        pass


def report_tk(exc_type, exc, tb):
    """Assign to the Tk root: app.report_callback_exception = crashlog.report_tk"""
    _write("ui callback", exc_type, exc, tb)
    try:
        traceback.print_exception(exc_type, exc, tb)
    except Exception:
        pass


def install(version: str = ""):
    global _version
    _version = version
    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook
'''

EDITS = [
    ("\nimport core\nimport elyby\n", "\nimport core\nimport crashlog\nimport elyby\n", 1),
    ('if __name__ == "__main__":\n    app = LauncherApp()\n    app.mainloop()\n',
     'if __name__ == "__main__":\n    crashlog.install(APP_VERSION)\n    app = LauncherApp()\n'
     '    app.report_callback_exception = crashlog.report_tk\n    app.mainloop()\n', 1),
]


def main():
    p = os.path.join(HERE, "gui.py")
    problems = []
    if os.path.exists(os.path.join(HERE, "crashlog.py")):
        problems.append("crashlog.py already exists (already applied?)")
    if not os.path.exists(p):
        problems.append("gui.py: not found")
    else:
        with open(p, "rb") as f:
            raw = f.read()
        crlf = b"\r\n" in raw
        text = raw.decode("utf-8").replace("\r\n", "\n")
        for old, new, count in EDITS:
            if text.count(old) != count:
                problems.append(f"gui.py: expected {count} match(es), found {text.count(old)} for: {old.strip().splitlines()[0][:60]}")
            else:
                text = text.replace(old, new)
    if problems:
        print("NOTHING CHANGED. Problems:")
        for pr in problems:
            print("  -", pr)
        sys.exit(1)

    with open(os.path.join(HERE, "crashlog.py"), "w", encoding="utf-8", newline="") as f:
        f.write(CRASHLOG)
    with open(p + ".bak", "wb") as f:
        f.write(raw)
    if crlf:
        text = text.replace("\n", "\r\n")
    with open(p, "wb") as f:
        f.write(text.encode("utf-8"))
    print("created crashlog.py and patched gui.py")
    print("\nDone. Next: py -m py_compile crashlog.py gui.py")


if __name__ == "__main__":
    main()
