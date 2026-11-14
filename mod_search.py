"""
mod_search.py - one-time script. Run from C:\\MCLauncher:   py mod_search.py

Adds a live search box above the mod list in Manage instance, so finding one mod in a
72-mod pack is a filename search instead of scrolling. Filters as you type, matches
anywhere in the filename (case-insensitive), e.g. "xaero" finds
"xaeros-minimap-1.20.1-forge-25.2.6.jar". Works on both the "Turned off" and active
sections; a header is only shown if at least one mod in that section still matches.

Only gui.py is touched (ManageInstanceDialog). Nothing is changed unless both edits
match exactly. Backup: gui.py.bak. LF and CRLF both fine.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

OLD_INIT = '''        self.mods_label = ctk.CTkLabel(self, text=tr("Mods"), anchor="w", font=ctk.CTkFont(weight="bold"))
        self.mods_label.pack(fill="x", padx=20, pady=(10, 0))
        self.mod_list = VirtualModList(self, self.do_toggle_mod, self.do_remove_mod)
        self.mod_list.pack(fill="both", expand=True, padx=20, pady=(5, 15))
        self.refresh_mods()
'''
NEW_INIT = '''        self.mods_label = ctk.CTkLabel(self, text=tr("Mods"), anchor="w", font=ctk.CTkFont(weight="bold"))
        self.mods_label.pack(fill="x", padx=20, pady=(10, 0))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        search_row = ctk.CTkFrame(self, fg_color="transparent")
        search_row.pack(fill="x", padx=20, pady=(6, 0))
        self.search_entry = ctk.CTkEntry(search_row, textvariable=self.search_var,
                                          placeholder_text=tr("Search mods..."))
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.clear_search_btn = ctk.CTkButton(search_row, text="\\u2715", width=28,
                                               fg_color="transparent", text_color=COLOR_TEXT_MUTED,
                                               hover_color=COLOR_BUTTON_SECONDARY_HOVER,
                                               command=lambda: self.search_var.set(""))
        self.clear_search_btn.pack(side="left", padx=(4, 0))
        self.mod_list = VirtualModList(self, self.do_toggle_mod, self.do_remove_mod)
        self.mod_list.pack(fill="both", expand=True, padx=20, pady=(5, 15))
        self._all_mods, self._all_off = [], []
        self.refresh_mods()
'''

# lazy_imports.py (if already applied) moves "import mod_doctor" to be the first line inside
# refresh_mods, so there are two possible shapes of the original method - try the one that
# already has the local import first, then the plain one, and keep that import exactly where
# lazy_imports.py put it (as the first line) either way.
OLD_REFRESH_WITH_IMPORT = '''    def refresh_mods(self):
        import mod_doctor
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
'''
NEW_REFRESH_WITH_IMPORT = '''    def refresh_mods(self):
        import mod_doctor
        self._all_mods = instances.list_mods(self.inst.name)
        self._all_off = mod_doctor.list_turned_off(self.inst.path)
        title = tr('Mods ({0})', len(self._all_mods)) + (
            ("   \\u00b7   " + tr("{0} off", len(self._all_off))) if self._all_off else "")
        self.mods_label.configure(text=title)
        self._apply_filter()

    def _apply_filter(self):'''

OLD_REFRESH_NO_IMPORT = '''    def refresh_mods(self):
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
'''
NEW_REFRESH_NO_IMPORT = '''    def refresh_mods(self):
        self._all_mods = instances.list_mods(self.inst.name)
        self._all_off = mod_doctor.list_turned_off(self.inst.path)
        title = tr('Mods ({0})', len(self._all_mods)) + (
            ("   \\u00b7   " + tr("{0} off", len(self._all_off))) if self._all_off else "")
        self.mods_label.configure(text=title)
        self._apply_filter()

    def _apply_filter(self):'''

REST_OF_FILTER = '''
        query = self.search_var.get().strip().lower()
        off = [f for f in self._all_off if query in f.lower()] if query else list(self._all_off)
        mods = [f for f in self._all_mods if query in f.lower()] if query else list(self._all_mods)
        items = []
        if off:
            items.append(("head", tr("Turned off ({0})", len(off))))
            items += [("mod", f, False) for f in off]
            items.append(("head", tr("Mods ({0})", len(mods))))
        items += [("mod", f, True) for f in mods]
        if query and not items:
            message = tr('No mods match "{0}".', self.search_var.get().strip())
        else:
            message = "" if items else tr("No mods in this instance.")
        self.mod_list.set_items(items, message)
        last = getattr(self, "_last_report", None)
        if last is not None:
'''


def read(path):
    with open(path, "rb") as f:
        raw = f.read()
    return raw.decode("utf-8").replace("\r\n", "\n"), b"\r\n" in raw


def main():
    p = os.path.join(HERE, "gui.py")
    if not os.path.exists(p):
        print("NOTHING CHANGED. gui.py not found."); sys.exit(1)
    with open(p, "rb") as f:
        raw = f.read()
    text, crlf = read(p)

    problems = []
    if text.count(OLD_INIT) != 1:
        problems.append(f"__init__ block: found {text.count(OLD_INIT)} match(es), expected 1")

    with_import = text.count(OLD_REFRESH_WITH_IMPORT)
    no_import = text.count(OLD_REFRESH_NO_IMPORT)
    if with_import == 1 and no_import == 0:
        old_refresh, new_refresh = OLD_REFRESH_WITH_IMPORT, NEW_REFRESH_WITH_IMPORT
    elif no_import == 1 and with_import == 0:
        old_refresh, new_refresh = OLD_REFRESH_NO_IMPORT, NEW_REFRESH_NO_IMPORT
    else:
        old_refresh = new_refresh = None
        problems.append(f"refresh_mods block: found {with_import} match(es) with a local "
                         f"'import mod_doctor' and {no_import} without; expected exactly one of the two to be 1")
    if problems:
        print("NOTHING CHANGED. Problems:")
        for pr in problems:
            print("  -", pr)
        sys.exit(1)

    text = text.replace(OLD_INIT, NEW_INIT, 1).replace(old_refresh, new_refresh + REST_OF_FILTER, 1)

    with open(p + ".bak", "wb") as f:
        f.write(raw)
    out = text.replace("\n", "\r\n") if crlf else text
    with open(p, "wb") as f:
        f.write(out.encode("utf-8"))
    print("patched gui.py: added search box to ManageInstanceDialog's mod list")
    print("\nDone. Next: py -m py_compile gui.py   then open Manage on any instance and type in the box.")


if __name__ == "__main__":
    main()
