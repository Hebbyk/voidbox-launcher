"""Manage dialog: (1) switching a mod off keeps it in the mod list under a "Turned off" header at the top
(foo.jar -> foo.jar.disabled in the mods folder, no more disabled_mods mix-up), and (2) the mod list only builds
the rows you can see, so big modpacks open instantly and scroll smoothly.
Run once from C:\\MCLauncher (after crash_suspect_patch.py):   py modlist_patch.py
Edits mod_doctor.py, gui.py, lang_ru.py, lang_uk.py (writes .modlist.bak first).
If any file is not what is expected, NOTHING is changed."""
import os, re, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))

MOD_DOCTOR_FUNCS = '''OFF_SUFFIX = ".disabled"


def list_turned_off(instance_path) -> list[str]:
    """Mods switched off in place (foo.jar -> foo.jar.disabled inside the mods folder)."""
    d = Path(instance_path) / "minecraft" / "mods"
    if not d.is_dir():
        return []
    return sorted((f.name for f in d.iterdir() if f.is_file() and f.name.lower().endswith(".jar" + OFF_SUFFIX)),
                  key=str.lower)


def turn_off(instance_path, filename: str) -> None:
    """Switches a mod off IN PLACE: foo.jar -> foo.jar.disabled. The game and the loaders ignore the file, and it
    stays in the mods folder so it can be switched straight back on."""
    if Path(filename).name != filename or not filename.lower().endswith(".jar"):
        raise OSError(f"Invalid mod filename: {filename}")
    mods = Path(instance_path) / "minecraft" / "mods"
    src, dst = mods / filename, mods / (filename + OFF_SUFFIX)
    if not src.is_file():
        raise OSError(f"'{filename}' isn't in the mods folder")
    if dst.exists():
        raise OSError(f"'{dst.name}' already exists - delete or switch on the old copy first")
    src.rename(dst)


def turn_on(instance_path, filename: str) -> None:
    """Switches a mod back on: foo.jar.disabled -> foo.jar. Refuses if foo.jar is already there."""
    if Path(filename).name != filename or not filename.lower().endswith(".jar" + OFF_SUFFIX):
        raise OSError(f"Invalid mod filename: {filename}")
    mods = Path(instance_path) / "minecraft" / "mods"
    src, dst = mods / filename, mods / filename[: -len(OFF_SUFFIX)]
    if not src.is_file():
        raise OSError(f"'{filename}' isn't in the mods folder")
    if dst.exists():
        raise OSError(f"A mod named '{dst.name}' is already switched on")
    src.rename(dst)


'''

VIRTUAL_LIST = '''class VirtualModList(ctk.CTkFrame):
    """A mod list that only builds the rows you can see. A normal scrolling frame builds (and keeps redrawing)
    thousands of widgets for a big modpack; this one keeps about 20 rows and re-uses them as you scroll."""
    ROW_H = 30

    def __init__(self, master, on_toggle, on_remove):
        super().__init__(master)
        self._on_toggle, self._on_remove = on_toggle, on_remove
        self.items = []          # ("head", text) | ("mod", filename, is_on)
        self.info = {}           # filename -> {"version": str, "chips": [(text, tone), ...]}
        self.message = ""
        self._ver = 0
        self._pool = []
        self._label_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"]
        bg = self._apply_appearance_mode(self._fg_color)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=bg, yscrollincrement=self.ROW_H)
        self.bar = ctk.CTkScrollbar(self, command=self._yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y", padx=(0, 2), pady=4)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        self.canvas.bind("<Configure>", lambda e: self._layout())
        self._bind_wheel(self.canvas)

    # ---- public ----
    def set_items(self, items, message=""):
        self.items, self.message = items, message
        self._layout()

    def set_info(self, info):
        self.info = info
        self._ver += 1
        self._layout()

    # ---- scrolling ----
    def _bind_wheel(self, w):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                w.bind(seq, self._wheel, add="+")
            except Exception:
                pass
        for c in w.winfo_children():
            self._bind_wheel(c)

    def _wheel(self, e):
        num = getattr(e, "num", 0)
        if num == 4:
            step = -3
        elif num == 5:
            step = 3
        else:
            d = getattr(e, "delta", 0)
            step = -3 if d > 0 else (3 if d < 0 else 0)
        if step and len(self.items) * self.ROW_H > self.canvas.winfo_height():
            self.canvas.yview_scroll(step, "units")
            self._layout()

    def _yview(self, *args):
        self.canvas.yview(*args)
        self._layout()

    # ---- rows ----
    def _make_slot(self):
        row = ctk.CTkFrame(self.canvas, fg_color="transparent", height=self.ROW_H)
        head = ctk.CTkLabel(row, text="", anchor="w", font=ctk.CTkFont(weight="bold"))
        body = ctk.CTkFrame(row, fg_color="transparent")
        slot = {"row": row, "head": head, "body": body, "key": None, "item": None}
        slot["btn"] = ctk.CTkButton(body, text="\\u2715", width=28, height=26, fg_color="transparent",
                                    text_color=COLOR_TEXT_MUTED, hover_color=COLOR_DESTRUCTIVE,
                                    command=lambda s=slot: self._remove(s))
        slot["btn"].pack(side="right", padx=(2, 0))
        slot["hold"] = ctk.CTkFrame(body, fg_color="transparent")
        slot["hold"].pack(side="right")
        slot["sw"] = ctk.CTkSwitch(body, text="", width=44, switch_width=34, switch_height=16)
        slot["sw"].pack(side="left")
        slot["lbl"] = ctk.CTkLabel(body, text="", anchor="w")
        slot["lbl"].pack(side="left", fill="x", expand=True)
        slot["win"] = self.canvas.create_window(0, 0, anchor="nw", window=row, height=self.ROW_H, state="hidden")
        self._bind_wheel(row)
        return slot

    def _toggle(self, slot):
        if slot["item"]:
            self._on_toggle(slot["item"][0], bool(slot["sw"].get()))

    def _remove(self, slot):
        if slot["item"]:
            self._on_remove(slot["item"][0], slot["item"][1])

    def _bind_slot(self, slot, item):
        if item[0] == "head":
            slot["item"] = None
            slot["body"].pack_forget()
            slot["head"].configure(text=item[1])
            slot["head"].pack(fill="x", padx=(6, 0))
            return
        _, filename, on = item
        slot["item"] = (filename, on)
        slot["head"].pack_forget()
        slot["body"].pack(fill="both", expand=True)
        low = filename.lower()
        stem = filename[:-13] if low.endswith(".jar.disabled") else (filename[:-4] if low.endswith(".jar") else filename)
        slot["lbl"].configure(text=stem, text_color=self._label_color if on else COLOR_TEXT_MUTED)
        sw = slot["sw"]
        sw.configure(command=None)                # select()/deselect() would otherwise fire the toggle
        sw.select() if on else sw.deselect()
        sw.configure(command=lambda s=slot: self._toggle(s))
        for w in slot["hold"].winfo_children():
            w.destroy()
        inf = self.info.get(filename) if on else None
        if inf:
            for text, tone in inf["chips"]:
                make_chip(slot["hold"], text, tone).pack(side="left", padx=(0, 6))
            if inf["version"]:
                ctk.CTkLabel(slot["hold"], text=inf["version"], text_color=COLOR_TEXT_MUTED,
                             font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))
            self._bind_wheel(slot["hold"])

    def _layout(self):
        h, w = max(self.canvas.winfo_height(), 1), max(self.canvas.winfo_width(), 1)
        n = len(self.items)
        self.canvas.configure(scrollregion=(0, 0, w, max(n * self.ROW_H, h)))
        while len(self._pool) < h // self.ROW_H + 4:
            self._pool.append(self._make_slot())
        size = len(self._pool)
        first = max(0, int(self.canvas.canvasy(0) // self.ROW_H))
        used = set()
        for i in range(first, min(n, first + size)):
            slot = self._pool[i % size]
            used.add(i % size)
            item = self.items[i]
            key = (item, self._ver if item[0] == "mod" else 0)
            if slot["key"] != key:
                self._bind_slot(slot, item)
                slot["key"] = key
            self.canvas.coords(slot["win"], 0, i * self.ROW_H)
            self.canvas.itemconfigure(slot["win"], width=w, state="normal")
        for k, slot in enumerate(self._pool):
            if k not in used and slot["key"] is not None:
                self.canvas.itemconfigure(slot["win"], state="hidden")
                slot["key"] = None
        self.canvas.delete("msg")
        if not self.items and self.message:
            self.canvas.create_text(w // 2, 40, text=self.message, fill=COLOR_TEXT_MUTED, tags="msg")


'''

NEW_METHODS = '''    def refresh_mods(self):
        mods = instances.list_mods(self.inst.name)
        off = mod_doctor.list_turned_off(self.inst.path)
        title = tr('Mods ({0})', len(mods)) + (("   \\u00b7   " + tr("{0} off", len(off))) if off else "")
        self.mods_label.configure(text=title)
        items = []
        if off:
            items.append(("head", tr("Turned off ({0})", len(off))))
            items += [("mod", f, False) for f in off]
            items.append(("head", tr("Mods ({0})", len(mods))))
        items += [("mod", f, True) for f in mods]
        self.mod_list.set_items(items, "" if items else tr("No mods in this instance."))
        last = getattr(self, "_last_report", None)
        if last is not None:
            self._decorate_rows(last)

    @staticmethod
    def _short_range(rng: str) -> str:
        m = re.fullmatch(r"\\[\\s*([\\w.\\-+]+)\\s*,\\s*\\)", rng.strip())      # "[21.1.262,)" -> "21.1.262+"
        return f"{m.group(1)}+" if m else rng

    def _decorate_rows(self, report, only=None):
        """Adds the version and any problem chips once the background scan has finished."""
        old_names = {l.name for l, _w, _m in report.plan.moves}
        bad = {p.jar: p for p in report.problems}
        info = {}
        for j in report.scanned:
            chips = []
            if j.name in old_names:
                chips.append((tr("Older copy"), CHIP_AMBER))
            if j.name in bad:
                p = bad[j.name]
                name = LauncherApp.LOADER_NAMES.get(p.target, p.target)
                chips.append((tr("Needs {0} {1}", name, self._short_range(p.wanted)), CHIP_RED))
            version = next(iter(j.mods.values()), "")
            info[j.name] = {"chips": chips, "version": str(version)[:22] if version and version != "?" else ""}
        self.mod_list.set_info(info)

'''

EXPECTED_DEFS = ["refresh_mods", "_build_rows", "_add_mod_row", "_short_range", "_decorate_rows"]

RU = {"Turned off ({0})": "Выключены ({0})"}
UK = {"Turned off ({0})": "Вимкнені ({0})"}

def dict_lines(d):
    return "".join("    %r: %r,\n" % (k, v) for k, v in d.items())

def main():
    if not os.path.exists(os.path.join(HERE, "crash_suspect.py")):
        sys.exit("Run crash_suspect_patch.py first (crash_suspect.py is missing). Nothing changed.")
    crlf, new = {}, {}
    def read(name):
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            sys.exit(f"{name} not found. Nothing changed.")
        with open(p, "r", encoding="utf-8", newline="") as f:
            raw = f.read()
        crlf[name] = "\r\n" in raw
        return raw.replace("\r\n", "\n")
    def once(text, old, name, n=1):
        if text.count(old) != n:
            sys.exit(f"{name}: expected {n} match(es) of\n  {old[:80]!r}\nbut found {text.count(old)}. Nothing changed.")

    t = read("mod_doctor.py")
    if "def turn_off(" in t:
        sys.exit("Already applied (mod_doctor.py has turn_off). Nothing changed.")
    anchor = "def enable_mod(instance_path, filename: str) -> None:"
    once(t, anchor, "mod_doctor.py")
    new["mod_doctor.py"] = t.replace(anchor, MOD_DOCTOR_FUNCS + anchor)

    g = read("gui.py")
    cls_anchor = "class ManageInstanceDialog(ModalDialog):"
    once(g, cls_anchor, "gui.py")
    g = g.replace(cls_anchor, VIRTUAL_LIST + cls_anchor)
    old_frame = ('        self.mods_frame = ctk.CTkScrollableFrame(self)\n'
                 '        self.mods_frame.pack(fill="both", expand=True, padx=20, pady=(5, 15))\n')
    once(g, old_frame, "gui.py")
    g = g.replace(old_frame, '        self.mod_list = VirtualModList(self, self.do_toggle_mod, self.do_remove_mod)\n'
                             '        self.mod_list.pack(fill="both", expand=True, padx=20, pady=(5, 15))\n')
    a, b = "    def refresh_mods(self):\n", "    def do_toggle_mod(self, filename: str, want_on: bool):\n"
    once(g, a, "gui.py"); once(g, b, "gui.py")
    i, j = g.index(a), g.index(b)
    if i > j:
        sys.exit("gui.py: unexpected order of the mod list methods. Nothing changed.")
    defs = re.findall(r"^    def (\w+)\(", g[i:j], re.M)
    if defs != EXPECTED_DEFS:
        sys.exit(f"gui.py: the mod list code is not what I expected (found {defs}). Nothing changed.")
    g = g[:i] + NEW_METHODS + g[j:]
    for old, rep in (
        ('(mod_doctor.enable_mod if want_on else mod_doctor.disable_mod)(self.inst.path, filename)',
         '(mod_doctor.turn_on if want_on else mod_doctor.turn_off)(self.inst.path, filename)'),
        ('                (mod_doctor.disabled_dir(self.inst.path) / filename).unlink()\n        except Exception as e:',
         '                (Path(self.inst.path) / "minecraft" / "mods" / filename).unlink()\n        except Exception as e:'),
        ('mod_doctor.disable_mod(Path(self._info["mc_dir"]).parent, sus["filename"])',
         'mod_doctor.turn_off(Path(self._info["mc_dir"]).parent, sus["filename"])'),
    ):
        once(g, old, "gui.py")
        g = g.replace(old, rep)
    new["gui.py"] = g

    for name, d in (("lang_ru.py", RU), ("lang_uk.py", UK)):
        t = read(name)
        body = t.rstrip()
        if not body.endswith("}"):
            sys.exit(f"{name}: does not end with a closing brace. Nothing changed.")
        if "Turned off (" in t:
            sys.exit(f"{name} already has the new string. Nothing changed.")
        head = body[:-1].rstrip()
        if not head.endswith(","):
            head += ","
        new[name] = head + "\n    # --- mod list: turned-off section\n" + dict_lines(d) + "}\n"

    for name, text in new.items():
        p = os.path.join(HERE, name)
        shutil.copy2(p, p + ".modlist.bak")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace("\n", "\r\n") if crlf[name] else text)
        print("patched", name)
    print("Done. Open Manage on a big modpack: it opens at once, and switched-off mods sit under 'Turned off' at the top.")

main()
