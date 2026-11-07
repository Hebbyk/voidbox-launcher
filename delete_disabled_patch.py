"""#10 - "Delete all" button for the switched-off mods in disabled_mods (next to "Restore all").
Run once from C:\\MCLauncher:   py delete_disabled_patch.py
Edits mod_doctor.py, gui.py, lang_ru.py, lang_uk.py (writes .deldis.bak first).
If any file is not what is expected, NOTHING is changed."""
import os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))

MOD_DOCTOR_OLD = '''def restore_all(instance_path):'''
MOD_DOCTOR_NEW = '''def delete_all_disabled(instance_path):
    """PERMANENTLY deletes every jar in disabled_mods (that includes mods switched off on purpose).
    Returns (deleted names, failed names). Removes the folder afterwards if it is empty."""
    d = disabled_dir(instance_path)
    deleted, failed = [], []
    for name in list_disabled(instance_path):
        try:
            (d / name).unlink()
            deleted.append(name)
        except OSError:
            failed.append(name)
    try:
        d.rmdir()      # only works when nothing is left in it
    except OSError:
        pass
    return deleted, failed


def restore_all(instance_path):'''

EDITS = {
    "mod_doctor.py": [(MOD_DOCTOR_OLD, MOD_DOCTOR_NEW, 1)],
    "gui.py": [
        ('        def card(title, body, color, button_text=None, command=None):\n',
         '        def card(title, body, color, button_text=None, command=None, extra_text=None, extra_command=None):\n', 1),
        ('            if button_text:\n                ctk.CTkButton(top, text=button_text, width=120, command=command, text_color=color,',
         '            if extra_text:\n'
         '                ctk.CTkButton(top, text=extra_text, width=100, command=extra_command, text_color="#FF8FAE",\n'
         '                              fg_color=COLOR_BUTTON_SECONDARY, hover_color=COLOR_BUTTON_SECONDARY_HOVER\n'
         '                              ).pack(side="right", padx=(8, 0))\n'
         '            if button_text:\n                ctk.CTkButton(top, text=button_text, width=120, command=command, text_color=color,', 1),
        ('                 tr("Restore all"), self.do_restore_disabled)\n',
         '                 tr("Restore all"), self.do_restore_disabled,\n'
         '                 tr("Delete all"), self.do_delete_disabled)\n', 1),
        ('    def do_import_world(self):\n',
         '    def do_delete_disabled(self):\n'
         '        names = mod_doctor.list_disabled(self.inst.path)\n'
         '        if not names:\n'
         '            return\n'
         '        text = tr("Permanently delete {0} switched-off mods? This includes mods you switched off yourself, and it can\'t be undone.", len(names))\n'
         '        text += "\\n\\n" + "\\n".join(names[:10])\n'
         '        if len(names) > 10:\n'
         '            text += "\\n" + tr("...and {0} more", len(names) - 10)\n'
         '        if not messagebox.askyesno(tr("Delete all"), text, icon="warning"):\n'
         '            return\n'
         '        deleted, failed = mod_doctor.delete_all_disabled(self.inst.path)\n'
         '        if failed:\n'
         '            messagebox.showerror(tr("Couldn\'t delete some files"),\n'
         '                                 tr("{0}\\n\\n(If Minecraft is running, close it and try again.)", "\\n".join(failed)))\n'
         '        self.refresh_mods()\n'
         '        self.refresh_health()\n'
         '\n'
         '    def do_import_world(self):\n', 1),
    ],
}

RU = {
    "Delete all": "Удалить все",
    "Permanently delete {0} switched-off mods? This includes mods you switched off yourself, and it can't be undone.":
        "Удалить навсегда выключенные моды ({0})? Среди них могут быть моды, которые вы отключили сами. Отменить это нельзя.",
}
UK = {
    "Delete all": "Видалити всі",
    "Permanently delete {0} switched-off mods? This includes mods you switched off yourself, and it can't be undone.":
        "Видалити назавжди вимкнені моди ({0})? Серед них можуть бути моди, які ви вимкнули самі. Скасувати це неможливо.",
}

def dict_lines(d):
    return "".join("    %r: %r,\n" % (k, v) for k, v in d.items())

def main():
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
        if "delete_all_disabled" in text and name == "mod_doctor.py":
            sys.exit("Already applied (mod_doctor.py has delete_all_disabled). Nothing changed.")
        for old, rep, n in edits:
            if text.count(old) != n:
                sys.exit(f"{name}: expected {n} match(es) of\n  {old[:70]!r}\nbut found {text.count(old)}. Nothing changed.")
            text = text.replace(old, rep)
        new[name] = text
    for name, d in (("lang_ru.py", RU), ("lang_uk.py", UK)):
        text = read(name)
        body = text.rstrip()
        if not body.endswith("}"):
            sys.exit(f"{name}: does not end with a closing brace. Nothing changed.")
        if '"Delete all"' in text or "'Delete all'" in text:
            sys.exit(f"{name} already has \"Delete all\". Nothing changed.")
        head = body[:-1].rstrip()
        if not head.endswith(","):
            head += ","
        new[name] = head + "\n    # --- delete leftovers in disabled_mods\n" + dict_lines(d) + "}\n"
    for name, text in new.items():
        p = os.path.join(HERE, name)
        shutil.copy2(p, p + ".deldis.bak")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace("\n", "\r\n") if crlf[name] else text)
        print("patched", name)
    print("Done. Test: Manage an instance that has switched-off mods -> the card now has a red \"Delete all\".")

main()
