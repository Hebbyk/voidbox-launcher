"""
atomicio - write a text file so a crash or power cut can never leave it half-written.
The new content goes to "<name>.tmp" first, then replaces the real file in one step.
"""
import json
import os
import shutil
import time
from pathlib import Path


def write_text(path, text, encoding="utf-8", backup=False):
    """Atomic replacement for Path.write_text. backup=True first keeps the previous
    copy as "<name>.bak", but only if that copy is valid JSON (so a broken file never
    overwrites a good backup)."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if backup and path.exists():
            try:
                json.loads(path.read_text(encoding=encoding))
                shutil.copy2(path, path.with_name(path.name + ".bak"))
            except (OSError, ValueError):
                pass
        for attempt in range(6):  # antivirus / indexers can hold the file for a moment on Windows
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.1 * (attempt + 1))
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
