"""Shortens 3 button labels in the Manage dialog (Russian + Ukrainian) so they stop being cut off.
Run once from C:\\MCLauncher:   py label_fix.py
Edits lang_ru.py and lang_uk.py (writes .bak first). If a line is not what is expected, NOTHING is changed."""
import os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
EDITS = {
    "lang_ru.py": [
        ('"Open Instance Folder": "Открыть папку экземпляра",', '"Open Instance Folder": "Открыть папку",'),
        ('"Check for updates": "Проверить обновления",', '"Check for updates": "Обновления модов",'),
        ("'World backups...': 'Резервные копии миров...',", "'World backups...': 'Копии миров...',"),
    ],
    "lang_uk.py": [
        ('"Open Instance Folder": "Відкрити папку екземпляра",', '"Open Instance Folder": "Відкрити папку",'),
        ('"Check for updates": "Перевірити оновлення",', '"Check for updates": "Оновлення модів",'),
        ('"World backups...": "Резервні копії світів...",', '"World backups...": "Копії світів...",'),
    ],
}
new = {}
for name, edits in EDITS.items():
    path = os.path.join(HERE, name)
    if not os.path.exists(path):
        sys.exit(f"{name} not found. Nothing changed.")
    with open(path, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    for old, rep in edits:
        if text.count(old) != 1:
            sys.exit(f"{name}: expected line not found exactly once:\n  {old}\nNothing changed (already applied?).")
        text = text.replace(old, rep)
    new[name] = text
for name, text in new.items():
    path = os.path.join(HERE, name)
    shutil.copy2(path, path + ".labels.bak")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("patched", name)
print("Done. Open an instance -> Manage: no more cut-off buttons.")
