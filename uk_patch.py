"""Adds Ukrainian to Voidbox Launcher. Run once from C:\\MCLauncher (needs lang_uk.py next to it):
    py uk_patch.py
Edits i18n.py, voidbox.spec, build.ps1 and voidbox.wxs in place (writes .bak copies first).
If any file is not what is expected, NOTHING is changed."""
import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
EDITS = {
    "i18n.py": [
        ('LANGUAGES = {"en": "English", "ru": "Русский"}',
         'LANGUAGES = {"en": "English", "ru": "Русский", "uk": "Українська"}'),
        ('    if code == "ru":\n        from lang_ru import RU\n        return RU\n',
         '    if code == "ru":\n        from lang_ru import RU\n        return RU\n'
         '    if code == "uk":\n        from lang_uk import UK\n        return UK\n'),
        ("interface language: English (default) and Russian.",
         "interface language: English (default), Russian and Ukrainian."),
    ],
    "voidbox.spec": [
        ('# The Russian dictionary is loaded on demand by i18n.py (only when Russian is selected).\nhiddenimports += ["lang_ru"]',
         '# The Russian and Ukrainian dictionaries are loaded on demand by i18n.py (only when selected).\nhiddenimports += ["lang_ru", "lang_uk"]'),
    ],
    "build.ps1": [
        ('"i18n.py", "lang_ru.py", "voidbox.spec"', '"i18n.py", "lang_ru.py", "lang_uk.py", "voidbox.spec"'),
    ],
    "voidbox.wxs": [
        ('Interface language picked on the wizard\'s language page: "en" or "ru".',
         'Interface language picked on the wizard\'s language page: "en", "ru" or "uk".'),
        ('<Control Id="LanguageChoice" Type="RadioButtonGroup" X="20" Y="60" Width="330" Height="60" Property="APPLANGUAGE">',
         '<Control Id="LanguageChoice" Type="RadioButtonGroup" X="20" Y="60" Width="330" Height="72" Property="APPLANGUAGE">'),
        ('            <RadioButton Value="ru" X="0" Y="24" Width="295" Height="16" Text="Russian" />\n',
         '            <RadioButton Value="ru" X="0" Y="24" Width="295" Height="16" Text="Russian" />\n'
         '            <RadioButton Value="uk" X="0" Y="48" Width="295" Height="16" Text="Ukrainian" />\n'),
    ],
}

def main():
    if not os.path.exists(os.path.join(HERE, "lang_uk.py")):
        sys.exit("lang_uk.py is not in this folder - put it next to uk_patch.py first. Nothing changed.")
    new_text = {}
    for name, edits in EDITS.items():
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            sys.exit(f"{name} not found. Nothing changed.")
        with open(path, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        crlf = "\r\n" in text
        norm = text.replace("\r\n", "\n")
        if '"uk"' in norm and name == "i18n.py":
            sys.exit("i18n.py already has Ukrainian - nothing to do.")
        for old, new in edits:
            if norm.count(old) != 1:
                sys.exit(f"{name}: expected text not found exactly once:\n  {old[:70]!r}\nNothing changed.")
            norm = norm.replace(old, new)
        new_text[name] = norm.replace("\n", "\r\n") if crlf else norm
    for name, text in new_text.items():
        path = os.path.join(HERE, name)
        if not os.path.exists(path + ".bak"):
            shutil.copy2(path, path + ".bak")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print("patched", name)
    print("Done. Test:  py gui.py  -> Settings -> Language -> Українська -> Restart now")

main()
