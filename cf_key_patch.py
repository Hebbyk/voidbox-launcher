"""#6 - CurseForge API key field in Settings (own key overrides the built-in one).
Run once from C:\\MCLauncher:   py cf_key_patch.py
Edits settings.py, gui.py, lang_ru.py, lang_uk.py (writes .cfkey.bak first).
If any file is not what is expected, NOTHING is changed."""
import os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))

SETTINGS_OLD = '''def save_curseforge_api_key(key: str):
    if key:
        _set("curseforge_api_key", key)
'''
SETTINGS_NEW = SETTINGS_OLD + '''

def has_own_curseforge_key() -> bool:
    """True when the person pasted their own key (as opposed to the built-in one)."""
    return bool(_get("curseforge_api_key"))


def clear_curseforge_api_key():
    try:
        import keyring
        keyring.delete_password(SERVICE, "curseforge_api_key")
    except Exception:
        pass
'''

GUI_HEIGHT_OLD = 'super().__init__(app, title=tr("Settings"), width=420, height=320)'
GUI_HEIGHT_NEW = 'super().__init__(app, title=tr("Settings"), width=420, height=480)'
GUI_UI_OLD = '        self.note = ctk.CTkLabel(self, text="", wraplength=360, text_color=COLOR_TEXT_MUTED)\n'
GUI_UI_NEW = '''        ctk.CTkLabel(self, text=tr("CurseForge API key (optional):")).pack(pady=(26, 4))
        key_row = ctk.CTkFrame(self, fg_color="transparent")
        key_row.pack()
        self.cf_entry = ctk.CTkEntry(key_row, width=230, show="\\u2022")
        self.cf_entry.pack(side="left", padx=(0, 6))
        ctk.CTkButton(key_row, text=tr("Save"), width=64, command=self._cf_save).pack(side="left", padx=(0, 6))
        self.cf_remove_btn = ctk.CTkButton(key_row, text=tr("Remove"), width=70, command=self._cf_remove,
                                           fg_color=COLOR_BUTTON_SECONDARY,
                                           hover_color=COLOR_BUTTON_SECONDARY_HOVER)
        self.cf_status = ctk.CTkLabel(self, text="", wraplength=360, text_color=COLOR_TEXT_MUTED)
        self.cf_status.pack(pady=(6, 0))
        ctk.CTkLabel(self, text=tr("Leave it empty to use the built-in key. You can get a free key at console.curseforge.com."),
                     wraplength=360, text_color=COLOR_TEXT_MUTED, font=ctk.CTkFont(size=11)).pack(pady=(2, 0))
        self._cf_refresh()
''' + GUI_UI_OLD
GUI_METHODS_OLD = '    def on_language(self, label: str):\n'
GUI_METHODS_NEW = '''    def _cf_refresh(self, message: str = ""):
        own = settings.has_own_curseforge_key()
        if own:
            self.cf_remove_btn.pack(side="left")
        else:
            self.cf_remove_btn.pack_forget()
        self.cf_status.configure(text=message or (tr("Using your own key.") if own else tr("Using the built-in key.")))

    def _cf_save(self):
        key = self.cf_entry.get().strip()
        if not key:
            return
        if len(key) < 20 or " " in key:
            self._cf_refresh(tr("That doesn't look like a CurseForge key."))
            return
        settings.save_curseforge_api_key(key)
        self.cf_entry.delete(0, "end")
        self._cf_refresh(tr("Key saved."))

    def _cf_remove(self):
        settings.clear_curseforge_api_key()
        self._cf_refresh(tr("Your key was removed."))

''' + GUI_METHODS_OLD

RU = {
    "CurseForge API key (optional):": "Ключ API CurseForge (необязательно):",
    "Save": "Сохранить",
    "Using your own key.": "Используется ваш ключ.",
    "Using the built-in key.": "Используется встроенный ключ.",
    "That doesn't look like a CurseForge key.": "Это не похоже на ключ CurseForge.",
    "Key saved.": "Ключ сохранён.",
    "Your key was removed.": "Ваш ключ удалён.",
    "Leave it empty to use the built-in key. You can get a free key at console.curseforge.com.":
        "Оставьте поле пустым, чтобы использовать встроенный ключ. Бесплатный ключ можно получить на console.curseforge.com.",
}
UK = {
    "CurseForge API key (optional):": "Ключ API CurseForge (необов'язково):",
    "Save": "Зберегти",
    "Using your own key.": "Використовується ваш ключ.",
    "Using the built-in key.": "Використовується вбудований ключ.",
    "That doesn't look like a CurseForge key.": "Це не схоже на ключ CurseForge.",
    "Key saved.": "Ключ збережено.",
    "Your key was removed.": "Ваш ключ видалено.",
    "Leave it empty to use the built-in key. You can get a free key at console.curseforge.com.":
        "Залиште поле порожнім, щоб використовувати вбудований ключ. Безкоштовний ключ можна отримати на console.curseforge.com.",
}

def dict_lines(d):
    return "".join("    %r: %r,\n" % (k, v) for k, v in d.items())

CRLF = {}

def read(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        sys.exit(f"{name} not found. Nothing changed.")
    with open(p, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    CRLF[name] = "\r\n" in text
    return text.replace("\r\n", "\n")

def once(text, old, name):
    if text.count(old) != 1:
        sys.exit(f"{name}: expected text not found exactly once:\n  {old[:80]!r}\nNothing changed (already applied?).")

def main():
    new = {}
    t = read("settings.py"); once(t, SETTINGS_OLD, "settings.py"); new["settings.py"] = t.replace(SETTINGS_OLD, SETTINGS_NEW)
    t = read("gui.py")
    for old, rep in ((GUI_HEIGHT_OLD, GUI_HEIGHT_NEW), (GUI_UI_OLD, GUI_UI_NEW), (GUI_METHODS_OLD, GUI_METHODS_NEW)):
        once(t, old, "gui.py"); t = t.replace(old, rep)
    new["gui.py"] = t
    for name, d, var in (("lang_ru.py", RU, "RU"), ("lang_uk.py", UK, "UK")):
        t = read(name)
        body = t.rstrip()
        if not body.endswith("}"):
            sys.exit(f"{name}: does not end with a closing brace. Nothing changed.")
        if "Key saved." in t:
            sys.exit(f"{name} already has the new strings. Nothing changed.")
        eol = "\n"
        add = dict_lines(d)
        new[name] = body[:-1].rstrip() + "," + eol if not body[:-1].rstrip().endswith(",") else body[:-1].rstrip() + eol
        new[name] += "    # --- settings: CurseForge key" + eol + add + "}" + eol
    for name, text in new.items():
        p = os.path.join(HERE, name)
        shutil.copy2(p, p + ".cfkey.bak")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text.replace("\n", "\r\n") if CRLF.get(name) else text)
        print("patched", name)
    print("Done. Test: py gui.py -> Settings -> paste a CurseForge key -> Save.")

main()
