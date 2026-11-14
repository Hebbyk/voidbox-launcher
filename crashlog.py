"""
crashlog - writes every uncaught error to a log file so a bug report can include it.
Location: %LOCALAPPDATA%\\MCLauncher\\logs\\launcher-errors.log (one older copy is kept as .old).
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
                f"{platform.platform()} | Python {platform.python_version()} | {kind} ===\n")
        body = "".join(traceback.format_exception(exc_type, exc, tb))
        entry = log_sanitizer.sanitize(head + body) + "\n"
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
