"""#2 - the crash helper names the suspected mod and offers "Disable this mod".
Run once from C:\\MCLauncher (after relay_patch.py and delete_disabled_patch.py):   py crash_suspect_patch.py
Creates crash_suspect.py; edits core.py, gui.py, build.ps1, lang_ru.py, lang_uk.py (writes .suspect.bak first).
If any file is not what is expected, NOTHING is changed."""
import os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))

CRASH_SUSPECT = r'''"""Finds the mod most likely behind a crash, so the crash panel can offer "Disable this mod".

It only READS the crash report / log and the jars in the instance's mods folder. The answer is a best guess,
never a certainty, so the panel words it as "suspected". Sources, strongest first:
  1. the loader's own loading-error blocks (Forge/NeoForge: "Mod File:", "Requested by:", "MOD loading issue for:")
  2. the crash report's "Suspected Mods:" section
  3. Fabric/Quilt "Mod 'Name' (id) ..." lines from an incompatible-mod-set error
  4. a mixin config named in the error (<id>.mixins.json)
  5. the first stack frame that belongs to a class found inside one of the installed mod jars
"""
import re
import zipfile
from pathlib import Path

import mod_doctor

# ids of the game and the loaders themselves: never offered for switching off
NOT_MODS = {"minecraft", "forge", "neoforge", "fml", "javafml", "lowcodefml", "mclanguage", "java",
            "fabricloader", "fabric-loader", "quilt_loader", "quilt-loader", "mixin"}

# stack frames from these packages are the game, the loader or a library - not a mod we could switch off
SKIP_PREFIXES = ("java.", "javax.", "jdk.", "sun.", "com.sun.", "net.minecraft.", "com.mojang.", "net.neoforged.",
                 "net.minecraftforge.", "cpw.mods.", "org.lwjgl.", "org.spongepowered.", "io.netty.", "com.google.",
                 "org.apache.", "it.unimi.", "oshi.", "org.objectweb.", "org.slf4j.", "net.fabricmc.", "org.quiltmc.",
                 "org.joml.", "org.jetbrains.", "kotlin.", "kotlinx.", "org.openjdk.", "com.electronwill.", "org.w3c.",
                 "org.xml.", "ca.weblite.", "com.ibm.", "org.codehaus.", "org.lwjgl3.")

MAX_TEXT = 600_000
ID = r"[A-Za-z0-9_.\-]{1,80}"

RE_FILE = re.compile(r"mod\s*file:\s*(.+?\.jar)\b", re.I)
RE_REQUESTED = re.compile(r"Requested by:\s*'(" + ID + r")'", re.I)
RE_ISSUE = re.compile(r"MOD loading issue for:\s*(" + ID + r")", re.I)
RE_SUSPECT_LINE = re.compile(r"^\s*(.+?)\s*\((" + ID + r")\)(?:,\s*Version:\s*(\S+))?\s*$")
RE_FABRIC = re.compile(r"Mod\s+'([^']+)'\s+\((" + ID + r")\)")
RE_MIXIN = re.compile(r"(?<![A-Za-z0-9_.\-])(" + ID + r")\.mixins?\.json", re.I)
RE_AT = re.compile(r"^\s*at\s+(\S.*)$", re.M)
RE_MODULE = re.compile(r"(?:[^\s(/]{1,60}/){0,4}?([A-Za-z0-9_.\-]{1,80})@[^\s/]{1,60}/")      # TRANSFORMER/<modid>@<version>/<class>...
RE_CLASS = re.compile(r"((?:[A-Za-z_$][\w$]*\.)+[A-Za-z_$][\w$]*)\.[\w$<>]+\(")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(MAX_TEXT)
    except OSError:
        return ""


def _suspect_section(text):
    """(name, modid) pairs listed under 'Suspected Mod(s):' in a crash report."""
    out = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.search(r"Suspected Mods?:\s*(.*)$", line, re.I)
        if not m:
            continue
        rest = m.group(1).strip()
        cands = [rest] if rest and rest.upper() != "NONE" else []
        if not cands:
            for nxt in lines[i + 1:i + 14]:
                s = nxt.strip()
                if not s or s.startswith("--") or s.lower().startswith(("issue tracker", "stacktrace", "details")):
                    if not s:
                        break
                    continue
                cands.append(nxt)
        for c in cands:
            mm = RE_SUSPECT_LINE.match(c)
            if mm and mm.group(2).lower() not in NOT_MODS:
                out.append((mm.group(1).strip(), mm.group(2)))
        if out:
            break
    return out


class _Jars:
    def __init__(self, mc_dir):
        self.mods_dir = Path(mc_dir) / "mods"
        self.jars = mod_doctor.scan(self.mods_dir) if self.mods_dir.is_dir() else []
        self._names = {}

    def by_filename(self, name):
        base = Path(str(name).replace("\\", "/")).name.lower()
        return next((j for j in self.jars if j.name.lower() == base), None)

    def by_modid(self, modid):
        if not modid or modid.lower() in NOT_MODS:
            return None
        hits = [j for j in self.jars if modid in j.mods]
        if not hits:
            low = modid.lower()
            hits = [j for j in self.jars if any(k.lower() == low for k in j.mods)]
        return max(hits, key=lambda j: j.mtime) if hits else None

    def by_mixin_name(self, stem):
        j = self.by_modid(stem)
        if j:
            return j
        for suf in ("-common", "_common", "-fabric", "_fabric", "-forge", "_forge", "-neoforge", "_neoforge",
                    "-quilt", "_quilt", ".common", "-mixins", "_mixins"):
            if stem.lower().endswith(suf):
                j = self.by_modid(stem[: -len(suf)])
                if j:
                    return j
        return None

    def by_class(self, dotted):
        path = dotted.split("$")[0].replace(".", "/") + ".class"
        for j in self.jars:
            names = self._names.get(j.name)
            if names is None:
                try:
                    with zipfile.ZipFile(j.path) as zf:
                        names = set(zf.namelist())
                except (zipfile.BadZipFile, OSError):
                    names = set()
                self._names[j.name] = names
            if path in names:
                return j
        return None


def _result(jar, name, modid, why):
    shown = name or modid or jar.name
    return {"filename": jar.name, "modid": modid, "name": shown, "why": why}


def find_suspect(mc_dir, crash_report=None, log_tail=None):
    """The most likely culprit as {'filename', 'modid', 'name', 'why'}, or None when nothing points at an
    installed mod. mc_dir is the instance's minecraft folder (the one that contains mods/ and logs/)."""
    jars = _Jars(mc_dir)
    if not jars.jars:
        return None
    parts = []
    if crash_report:
        parts.append(_read(crash_report))
    parts.append("\n".join(log_tail or []))
    text = "\n".join(p for p in parts if p)
    if not text.strip():
        return None

    # 1. the loader's own loading-error blocks
    for m in RE_REQUESTED.finditer(text):          # "Mod ID: 'x' (missing), Requested by: 'y'": y can't load
        j = jars.by_modid(m.group(1))
        if j:
            return _result(j, None, m.group(1), "loader")
    for m in RE_FILE.finditer(text):
        j = jars.by_filename(m.group(1))
        if j:
            return _result(j, None, None, "loader")
    for m in RE_ISSUE.finditer(text):
        j = jars.by_modid(m.group(1))
        if j:
            return _result(j, None, m.group(1), "loader")

    # 2. 'Suspected Mods:' section of the crash report
    for name, modid in _suspect_section(text):
        j = jars.by_modid(modid)
        if j:
            return _result(j, name, modid, "suspect")

    # 3. Fabric / Quilt incompatible mod set
    for m in RE_FABRIC.finditer(text):
        j = jars.by_modid(m.group(2))
        if j:
            return _result(j, m.group(1), m.group(2), "fabric")

    # 4. mixin config
    for m in RE_MIXIN.finditer(text):
        stem = m.group(1)
        if stem.lower() in ("mixins", "mixin", "default"):
            continue
        j = jars.by_mixin_name(stem)
        if j:
            return _result(j, None, stem, "mixin")

    # 5. first stack frame that belongs to an installed mod
    seen = 0
    for m in RE_AT.finditer(text):
        frame = m.group(1)
        mm = RE_MODULE.match(frame)                  # NeoForge/Forge frames name the mod: .../<modid>@<version>/...
        if mm and mm.group(1).lower() not in NOT_MODS:
            j = jars.by_modid(mm.group(1))
            if j:
                return _result(j, None, mm.group(1), "stack")
        cm = RE_CLASS.search(frame)
        if not cm or cm.group(1).startswith(SKIP_PREFIXES):
            continue
        j = jars.by_class(cm.group(1))
        if j:
            ids = list(j.mods)
            return _result(j, None, ids[0] if ids else None, "stack")
        seen += 1
        if seen > 80:
            break
    return None
'''

EDITS = {
    "core.py": [
        ('    info["highlights"] = _key_lines(info["tail"])\n',
         '    info["highlights"] = _key_lines(info["tail"])\n'
         '    try:\n'
         '        import crash_suspect\n'
         '        info["suspect"] = crash_suspect.find_suspect(mc_dir, crash, info["tail"])\n'
         '    except Exception as e:      # a guess is never worth breaking the crash panel for\n'
         '        print(f"[core] couldn\'t look for a suspect mod: {e}")\n'
         '        info["suspect"] = None\n', 1),
    ],
    "gui.py": [
        ('        ctk.CTkLabel(self, text=tr("It ran for {0} seconds.", info["seconds"]), anchor="w",\n'
         '                     text_color=COLOR_TEXT_MUTED).pack(fill="x", padx=14)\n',
         '        ctk.CTkLabel(self, text=tr("It ran for {0} seconds.", info["seconds"]), anchor="w",\n'
         '                     text_color=COLOR_TEXT_MUTED).pack(fill="x", padx=14)\n'
         '        self._suspect = info.get("suspect")\n'
         '        if self._suspect:\n'
         '            srow = ctk.CTkFrame(self, fg_color="transparent")\n'
         '            srow.pack(fill="x", padx=14, pady=(6, 0))\n'
         '            self._sus_btn = ctk.CTkButton(srow, text=tr("Disable this mod"), width=150, command=self._disable_suspect,\n'
         '                                          fg_color=COLOR_BUTTON_SECONDARY,\n'
         '                                          hover_color=COLOR_BUTTON_SECONDARY_HOVER)\n'
         '            self._sus_btn.pack(side="right")\n'
         '            self._sus_label = ctk.CTkLabel(srow, text=tr("Suspected mod: {0}", self._suspect["name"]), anchor="w",\n'
         '                                           justify="left", wraplength=300, font=ctk.CTkFont(weight="bold"))\n'
         '            self._sus_label.pack(side="left", fill="x", expand=True)\n', 1),
        ('    def _copy(self):\n',
         '    def _disable_suspect(self):\n'
         '        sus = self._suspect\n'
         '        try:\n'
         '            mod_doctor.disable_mod(Path(self._info["mc_dir"]).parent, sus["filename"])\n'
         '        except OSError as e:\n'
         '            self._sus_label.configure(text=tr("Couldn\'t disable it: {0}", e))\n'
         '            return\n'
         '        self._sus_btn.configure(state="disabled", text=tr("Disabled"))\n'
         '        self._sus_label.configure(text=tr("{0} is switched off. Press Play to try again; you can switch it back on in Manage.", sus["name"]))\n'
         '\n'
         '    def _copy(self):\n', 1),
    ],
    "build.ps1": [
        ('"cf_net.py", "voidbox.wxs"', '"cf_net.py", "crash_suspect.py", "voidbox.wxs"', 1),
    ],
}

RU = {
    "Suspected mod: {0}": "Подозрительный мод: {0}",
    "Disable this mod": "Отключить этот мод",
    "Disabled": "Отключён",
    "Couldn't disable it: {0}": "Не удалось отключить: {0}",
    "{0} is switched off. Press Play to try again; you can switch it back on in Manage.":
        "{0} выключен. Нажмите «Играть», чтобы попробовать снова; включить его обратно можно в «Управление».",
}
UK = {
    "Suspected mod: {0}": "Підозрілий мод: {0}",
    "Disable this mod": "Вимкнути цей мод",
    "Disabled": "Вимкнено",
    "Couldn't disable it: {0}": "Не вдалося вимкнути: {0}",
    "{0} is switched off. Press Play to try again; you can switch it back on in Manage.":
        "{0} вимкнено. Натисніть «Грати», щоб спробувати ще раз; увімкнути його знову можна в «Керування».",
}

def dict_lines(d):
    return "".join("    %r: %r,\n" % (k, v) for k, v in d.items())

def main():
    if os.path.exists(os.path.join(HERE, "crash_suspect.py")):
        sys.exit("crash_suspect.py already exists - looks like this patch was already applied. Nothing changed.")
    new, crlf = {}, {}
    def read(name):
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            sys.exit(f"{name} not found. Nothing changed.")
        with open(p, "r", encoding="utf-8", newline="") as f:
            raw = f.read()
        crlf[name] = "\r\n" in raw
        return raw.replace("\r\n", "\n")
    for name, edits in EDITS.items():
        text = read(name)
        for old, rep, n in edits:
            if text.count(old) != n:
                hint = " (run relay_patch.py first?)" if name == "build.ps1" else ""
                sys.exit(f"{name}: expected {n} match(es) of\n  {old[:70]!r}\nbut found {text.count(old)}{hint}. Nothing changed.")
            text = text.replace(old, rep)
        new[name] = text
    for name, d in (("lang_ru.py", RU), ("lang_uk.py", UK)):
        text = read(name)
        body = text.rstrip()
        if not body.endswith("}"):
            sys.exit(f"{name}: does not end with a closing brace. Nothing changed.")
        if "Disable this mod" in text:
            sys.exit(f"{name} already has the new strings. Nothing changed.")
        head = body[:-1].rstrip()
        if not head.endswith(","):
            head += ","
        new[name] = head + "\n    # --- crash helper: suspected mod\n" + dict_lines(d) + "}\n"
    for name, text in new.items():
        p = os.path.join(HERE, name)
        shutil.copy2(p, p + ".suspect.bak")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace("\n", "\r\n") if crlf[name] else text)
        print("patched", name)
    with open(os.path.join(HERE, "crash_suspect.py"), "w", encoding="utf-8", newline="") as f:
        f.write(CRASH_SUSPECT)
    print("created crash_suspect.py")
    print("Done. Test: make a mod crash the game -> the crash panel names it and offers Disable this mod.")

main()
