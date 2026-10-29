# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Voidbox Launcher. Build with build.ps1 (or: py -m PyInstaller voidbox.spec)
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

HERE = SPECPATH  # folder containing this spec — all paths below are absolute from it

datas = [(os.path.join(HERE, "theme_violet_nebula.json"), "."),
         (os.path.join(HERE, "icon.ico"), ".")]
binaries, hiddenimports = [], []

# Pillow loads its Tk bridge dynamically, so static analysis misses it and every
# image in the UI (instance icons, badges) crashes the frozen app without these.
hiddenimports += ["PIL._tkinter_finder", "PIL._imagingtk", "PIL.ImageTk"]

# Built-in CurseForge key: _cfk.py is generated locally by make_key.py (never shared).
# settings.py imports it inside try/except, so a build without it still works (it just asks).
if os.path.exists(os.path.join(HERE, "_cfk.py")):
    hiddenimports += ["_cfk"]
else:
    print("[spec] NOTE: no _cfk.py - this build has NO built-in CurseForge key (run make_key.py first)")

# License tripwire + build tag (see license_guard.py / canary.py)
for _m in ("license_guard", "_canary"):
    if os.path.exists(os.path.join(HERE, _m + ".py")):
        hiddenimports += [_m]

# The Russian dictionary is loaded on demand by i18n.py (only when Russian is selected).
hiddenimports += ["lang_ru"]

# customtkinter ships theme json + fonts that must travel with it.
# webview/pythonnet/clr_loader: Microsoft login window. keyring: saved sessions
# (its backends are discovered dynamically, so static analysis misses them).
for pkg in ("customtkinter", "webview", "pythonnet", "clr_loader", "keyring"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:
        print(f"[spec] WARNING: couldn't collect '{pkg}' ({type(e).__name__}) — is it installed?")
try:
    datas += copy_metadata("keyring")
    hiddenimports += collect_submodules("keyring.backends")
except Exception as e:
    print(f"[spec] WARNING: keyring metadata/backends not collected ({type(e).__name__})")

a = Analysis([os.path.join(HERE, "gui.py")], pathex=[HERE],
             datas=datas, binaries=binaries, hiddenimports=hiddenimports)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Voidbox Launcher",
          console=False, icon=os.path.join(HERE, "icon.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="VoidboxLauncher")
