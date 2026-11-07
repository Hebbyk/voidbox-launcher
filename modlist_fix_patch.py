"""Fix for the mouse-wheel error ('str' object has no attribute 'master') after modlist_patch.py:
  1. a guard so customtkinter's scroll handler can't crash on a wheel event that arrives as text instead of a widget
  2. the version/chip labels of each mod row are created once and shown/hidden, never destroyed while scrolling
Run once from C:\\MCLauncher (after modlist_patch.py):   py modlist_fix_patch.py
Edits gui.py only (writes gui.py.modfix.bak first). If anything is not what is expected, NOTHING is changed."""
import os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))

GUARD = '''# customtkinter's global mouse-wheel handler assumes event.widget is always a widget; when Tk hands it the
# widget's name as text it crashes with "'str' object has no attribute 'master'". Turn the name back into a widget
# (or ignore the event) instead.
_ctk_check_canvas = ctk.CTkScrollableFrame.check_if_master_is_canvas


def _safe_check_if_master_is_canvas(self, widget):
    if isinstance(widget, str):
        try:
            widget = self.nametowidget(widget)
        except Exception:
            return False
    return _ctk_check_canvas(self, widget)


ctk.CTkScrollableFrame.check_if_master_is_canvas = _safe_check_if_master_is_canvas


'''

EDITS = [
    ('class VirtualModList(ctk.CTkFrame):', GUARD + 'class VirtualModList(ctk.CTkFrame):', 1),
    ('        slot["hold"] = ctk.CTkFrame(body, fg_color="transparent")\n        slot["hold"].pack(side="right")\n',
     '        slot["hold"] = ctk.CTkFrame(body, fg_color="transparent")\n        slot["hold"].pack(side="right")\n'
     '        slot["chips"] = [make_chip(slot["hold"], "", CHIP_AMBER), make_chip(slot["hold"], "", CHIP_RED)]\n'
     '        slot["ver"] = ctk.CTkLabel(slot["hold"], text="", text_color=COLOR_TEXT_MUTED, font=ctk.CTkFont(size=11))\n', 1),
    ('        for w in slot["hold"].winfo_children():\n'
     '            w.destroy()\n'
     '        inf = self.info.get(filename) if on else None\n'
     '        if inf:\n'
     '            for text, tone in inf["chips"]:\n'
     '                make_chip(slot["hold"], text, tone).pack(side="left", padx=(0, 6))\n'
     '            if inf["version"]:\n'
     '                ctk.CTkLabel(slot["hold"], text=inf["version"], text_color=COLOR_TEXT_MUTED,\n'
     '                             font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 4))\n'
     '            self._bind_wheel(slot["hold"])\n',
     '        for w in (*slot["chips"], slot["ver"]):\n'
     '            w.pack_forget()          # hide, never destroy: a destroyed widget can still be named by a queued wheel event\n'
     '        inf = self.info.get(filename) if on else None\n'
     '        if inf:\n'
     '            for chip, (text, tone) in zip(slot["chips"], inf["chips"]):\n'
     '                chip.configure(text=f"  {text}  ", fg_color=tone[0], text_color=tone[1])\n'
     '                chip.pack(side="left", padx=(0, 6))\n'
     '            if inf["version"]:\n'
     '                slot["ver"].configure(text=inf["version"])\n'
     '                slot["ver"].pack(side="left", padx=(0, 4))\n', 1),
]

def main():
    p = os.path.join(HERE, "gui.py")
    if not os.path.exists(p):
        sys.exit("gui.py not found. Nothing changed.")
    with open(p, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    if "_safe_check_if_master_is_canvas" in text:
        sys.exit("Already applied. Nothing changed.")
    if "class VirtualModList(" not in text:
        sys.exit("Run modlist_patch.py first (the new mod list is missing). Nothing changed.")
    for old, rep, n in EDITS:
        if text.count(old) != n:
            sys.exit(f"gui.py: expected {n} match(es) of\n  {old[:80]!r}\nbut found {text.count(old)}. Nothing changed.")
        text = text.replace(old, rep)
    shutil.copy2(p, p + ".modfix.bak")
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\n", "\r\n") if crlf else text)
    print("patched gui.py")
    print("Done. Open Manage on a big pack and scroll fast with the mouse wheel: no more errors in the console.")

main()
