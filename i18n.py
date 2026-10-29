"""
mc_launcher.i18n — interface language: English (default) and Russian.

tr("English text") returns the text in the current language. The English text IS
the key, so anything without a translation simply shows in English — nothing can
come out blank or crash. Placeholders are positional format fields:

    tr("Adding {0} to {1}...", mod_name, instance_name)

Where the language comes from, in order:
  1. config.json in the launcher's data folder (set from the Settings dialog);
  2. the installer's choice, which the MSI writes to the registry
     (HKCU\\Software\\Hebby\\VoidboxLauncher\\Language). It is used on the first
     run, and again whenever the installer is run with a different choice, so a
     later choice in the installer wins over an older one in the app;
  3. English.
"""
import json
import os
import sys
from pathlib import Path

LANGUAGES = {"en": "English", "ru": "Русский"}
DEFAULT_LANGUAGE = "en"
REGISTRY_KEY = r"Software\Hebby\VoidboxLauncher"

_language = DEFAULT_LANGUAGE
_strings: dict = {}


def config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path.home() / ".local" / "share"
    return base / "MCLauncher" / "config.json"


def _read_config() -> dict:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_config(data: dict) -> None:
    try:
        config_path().parent.mkdir(parents=True, exist_ok=True)
        config_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        print(f"[i18n] couldn't save settings ({type(e).__name__})")


def _installer_language() -> str | None:
    """The language picked in the MSI wizard, if any (Windows only)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "Language")
        return value if value in LANGUAGES else None
    except OSError:
        return None


def _dictionary(code: str) -> dict:
    if code == "ru":
        from lang_ru import RU
        return RU
    return {}


def set_language(code: str) -> None:
    global _language, _strings
    _language = code if code in LANGUAGES else DEFAULT_LANGUAGE
    _strings = _dictionary(_language)


def current_language() -> str:
    return _language


def save_language(code: str) -> None:
    config = _read_config()
    config["language"] = code if code in LANGUAGES else DEFAULT_LANGUAGE
    _write_config(config)


def init() -> str:
    """Call once at startup, before any tr(). Returns the language in use."""
    config = _read_config()
    installer = _installer_language()
    code = config.get("language")
    if installer and installer != config.get("installer_language"):
        # first run after install, or the installer was run again with a different choice
        code = installer
        config.update(language=code, installer_language=installer)
        _write_config(config)
    elif code not in LANGUAGES:
        code = DEFAULT_LANGUAGE
        config["language"] = code
        _write_config(config)
    set_language(code)
    return code


def tr_to(code: str, text: str, *args) -> str:
    """Translate into a specific language regardless of the current one (used to
    show a note in the language you have just picked, before restarting)."""
    out = _dictionary(code).get(text, text)
    return out.format(*args) if args else out


def tr(text: str, *args) -> str:
    out = _strings.get(text, text)
    return out.format(*args) if args else out
