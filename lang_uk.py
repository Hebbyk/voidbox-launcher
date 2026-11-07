"""
mc_launcher.lang_uk — Ukrainian translations (English text -> Ukrainian).

The key is the exact English text passed to tr(); {0}, {1}, ... are placeholders
and must appear in the translation too (the order may differ). A missing entry just
shows in English. Terminology: instance = екземпляр, modpack = збірка, mod = мод,
loader = завантажувач, "premium" = ліцензія. ely.by is always written as "ely.by".
"""

UK = {
    # --- sidebar / accounts
    "Account": "Обліковий запис",
    "Not logged in": "Вхід не виконано",
    "Login (ely.by)": "Вхід (ely.by)",
    "Login (Microsoft)": "Вхід (Microsoft)",
    "Logged in:\n{0} (ely.by)": "Ви увійшли як:\n{0} (ely.by)",
    "Logged in:\n{0} (premium)": "Ви увійшли як:\n{0} (ліцензія)",
    "Logging in with Microsoft...": "Вхід через Microsoft...",
    "Login failed": "Помилка входу",
    "ely.by username:": "Ім'я користувача ely.by:",
    "ely.by password:": "Пароль ely.by:",
    "Log in (ely.by or Microsoft) first.": "Спочатку увійдіть (ely.by або Microsoft).",
    "+ Add Instance": "+ Додати екземпляр",
    "Refresh": "Оновити",
    "Output": "Вивід",

    # --- tabs / lists / search
    "Instances": "Екземпляри",
    "Browse": "Огляд",
    "Your Instances": "Ваші екземпляри",
    "Results": "Результати",
    "Search instances (name, loader, version)...": "Пошук екземплярів (назва, завантажувач, версія)...",
    "Search modpacks...": "Пошук збірок...",
    "Search mods...": "Пошук модів...",
    "Search": "Пошук",
    "Search failed": "Помилка пошуку",
    "Searching for '{0}'...": "Пошук «{0}»...",
    "No results.": "Нічого не знайдено.",
    "No instances yet — click + Add Instance": "Екземплярів поки немає — натисніть «+ Додати екземпляр»",
    "No instances match \"{0}\"": "Немає екземплярів, що відповідають «{0}»",
    "Adding mods to: {0}  ({1} on Minecraft {2})": "Додавання модів до: {0}  ({1} на Minecraft {2})",
    "Cancel": "Скасувати",
    "← Back to results": "← Назад до результатів",
    "Loading details...": "Завантаження відомостей...",
    "Couldn't load full details ({0}) — showing what search already had.":
        "Не вдалося завантажити повні відомості ({0}) — показано те, що вже було в результатах пошуку.",
    "Latest changelog:": "Останні зміни:",

    # --- instance rows / actions
    "Play": "Грати",
    "Export": "Експорт",
    "Delete": "Видалити",
    "Launching {0}...": "Запуск {0}...",
    "Launch failed": "Не вдалося запустити",
    "Delete instance": "Видалення екземпляра",
    "Delete '{0}'? This also deletes its files (mods, saves, etc.).":
        "Видалити «{0}»? Його файли (моди, збереження тощо) також буде видалено.",
    "Some files couldn't be deleted": "Не вдалося видалити деякі файли",
    "'{0}' was removed from the list, but {1} file(s) couldn't be deleted — probably still in use (close Minecraft/Java first if it's running):\n\n{2}":
        "«{0}» видалено зі списку, але не вдалося видалити файли ({1}) — імовірно, вони використовуються (якщо Minecraft запущено, спершу закрийте Minecraft/Java):\n\n{2}",

    # --- add instance / import
    "Add Instance": "Додати екземпляр",
    "Instance name:": "Назва екземпляра:",
    "Minecraft version (e.g. 1.20.1):": "Версія Minecraft (наприклад, 1.20.1):",
    "Loader:": "Завантажувач:",
    "Create Blank Instance": "Створити порожній екземпляр",
    "Import from Pack File (.mrpack / .zip)": "Імпорт із файлу збірки (.mrpack / .zip)",
    "Missing info": "Не вистачає даних",
    "Enter a name and Minecraft version.": "Введіть назву та версію Minecraft.",
    "Enter a name first.": "Спочатку введіть назву.",
    "Select a modpack file": "Виберіть файл збірки",
    "Modpack files": "Файли збірок",
    "All files": "Усі файли",
    "CurseForge API Key": "Ключ API CurseForge",
    "This looks like a CurseForge pack — paste your API key:":
        "Схоже, це збірка CurseForge — вставте свій ключ API:",
    "Importing {0}...": "Імпорт {0}...",
    "Importing {0}... ({1}/{2})": "Імпорт {0}... ({1}/{2})",
    "'{0}' imported successfully.": "«{0}» успішно імпортовано.",
    "Import failed": "Помилка імпорту",
    "Done": "Готово",

    # --- install from search
    "Install: {0}": "Встановлення: {0}",
    "Install": "Встановити",
    "Version:": "Версія:",
    "Loading...": "Завантаження...",
    "No versions found": "Версій не знайдено",
    "Couldn't load versions": "Не вдалося завантажити версії",
    "Enter a name and wait for versions to load.": "Введіть назву та дочекайтеся завантаження версій.",
    "Pick a version": "Виберіть версію",
    "Select a version first.": "Спочатку виберіть версію.",
    "Downloading {0}...": "Завантаження {0}...",
    "Installing {0}...": "Встановлення {0}...",
    "Installing {0}... ({1}/{2})": "Встановлення {0}... ({1}/{2})",
    "'{0}' installed successfully.": "«{0}» успішно встановлено.",
    "Install failed": "Помилка встановлення",

    # --- manage instance / add mods
    "Manage: {0}": "Керування: {0}",
    "Change Icon...": "Змінити значок...",
    "Choose an icon image": "Виберіть зображення значка",
    "Images": "Зображення",
    "Couldn't set icon": "Не вдалося встановити значок",
    "Rename": "Перейменувати",
    "Rename failed": "Не вдалося перейменувати",
    "Open Instance Folder": "Відкрити папку",
    "Couldn't open folder": "Не вдалося відкрити папку",
    "Add Mods...": "Додати моди...",
    "Mods": "Моди",
    "Mods ({0})": "Моди ({0})",
    "No mods in this instance.": "У цьому екземплярі немає модів.",
    "Remove": "Видалити",
    "Remove mod": "Видалення мода",
    "Delete '{0}' from {1}?": "Видалити «{0}» з {1}?",
    "Couldn't remove mod": "Не вдалося видалити мод",
    "{0}\n\n(If Minecraft is running, close it and try again.)":
        "{0}\n\n(Якщо Minecraft запущено, закрийте його та повторіть спробу.)",
    "Add to {0}: {1}": "Додати до {0}: {1}",
    "Compatible builds for {0} {1}:": "Сумісні версії для {0} {1}:",
    "No build of '{0}' found for {1} {2}.": "Для {1} {2} не знайдено версію «{0}».",
    "Couldn't load builds": "Не вдалося завантажити версії",
    "Pick a build": "Виберіть версію",
    "Select a build first.": "Спочатку виберіть версію.",
    "Add to Instance": "Додати до екземпляра",
    "Adding...": "Додавання...",
    "Downloading...": "Завантаження...",
    "Downloading... {0}%": "Завантаження... {0}%",
    "Added": "Додано",
    "'{0}' added to {1}.": "«{0}» додано до {1}.",
    "Add failed": "Не вдалося додати",

    # --- export
    "Export: {0}": "Експорт: {0}",
    "Format:": "Формат:",
    "Save to:": "Зберегти в:",
    "(not chosen)": "(не вибрано)",
    "Browse...": "Огляд...",
    "Choose export folder": "Виберіть папку для експорту",
    "Choose export file": "Виберіть файл для експорту",
    "Choose where to save first.": "Спочатку виберіть, куди зберегти.",
    "Exporting...": "Експорт...",
    "Exporting... {0}%": "Експорт... {0}%",
    "Exported to:\n{0}": "Експортовано до:\n{0}",
    "Export failed": "Помилка експорту",

    # --- updates
    "Voidbox Launcher {0} is available (you have {1}).": "Доступна версія Voidbox Launcher {0} (у вас {1}).",
    "Update now": "Оновити зараз",
    "Later": "Пізніше",
    "Downloading {0}... {1}%": "Завантаження {0}... {1}%",
    "Installer opened. Closing Voidbox Launcher so it can update...":
        "Інсталятор відкрито. Voidbox Launcher закривається, щоб оновитися...",
    "Update failed.": "Не вдалося оновити.",
    "Update failed": "Помилка оновлення",

    # --- settings
    "Settings": "Налаштування",
    "Language:": "Мова:",
    "Version {0}": "Версія {0}",
    "Language changed. Restart Voidbox Launcher to apply it.":
        "Мову змінено. Перезапустіть Voidbox Launcher, щоб застосувати її.",
    "Restart now": "Перезапустити зараз",
    "Couldn't restart": "Не вдалося перезапустити",

    # --- misc
    "Couldn't start the installer: {0}": "Не вдалося запустити інсталятор: {0}",
    "\n\nYou can download it manually:\n{0}": "\n\nВи можете завантажити його вручну:\n{0}",
    "(no description)": "(немає опису)",
    "Need a CurseForge API key to list files for this pack.":
        "Потрібен ключ API CurseForge, щоб отримати список файлів цієї збірки.",
    "Need a CurseForge API key to list files for this mod.":
        "Потрібен ключ API CurseForge, щоб отримати список файлів цього мода.",

    # --- crash helper
    "Minecraft closed with an error (exit code {0})": "Minecraft закрився з помилкою (код виходу {0})",
    "It ran for {0} seconds.": "Він пропрацював {0} с.",
    "No new log was written, so Minecraft stopped before it could log anything. This usually means a Java or launch-argument problem.":
        "Новий лог не створено: Minecraft зупинився раніше, ніж устиг щось записати. Зазвичай це означає, що проблема з Java або з аргументами запуску.",
    "Crash report: {0}": "Звіт про збій: {0}",
    "Copy log": "Копіювати лог",
    "Copied!": "Скопійовано!",
    "(no log was written)": "(лог не було створено)",
    "Open log folder": "Відкрити папку з логами",

    # --- mod health / world import
    "Import World...": "Імпорт світу...",
    "Checking mods...": "Перевірка модів...",
    "Couldn't check mods: {0}": "Не вдалося перевірити моди: {0}",
    "{0} mods have an old extra copy": "Модів із зайвою старою копією: {0}",
    "Keeps the newest of each and moves the rest to the disabled_mods folder. Nothing is deleted.":
        "Залишає найновішу версію кожного мода, а решту переносить до папки disabled_mods. Нічого не видаляється.",
    "Fix duplicates": "Виправити дублікати",
    "{0} need a manual look": "Потребують ручної перевірки: {0}",
    "These also provide other mods, so they were left alone: {0}":
        "Вони містять і інші моди, тому їх не чіпали: {0}",
    "Needs a newer loader or game version": "Потрібен новіший завантажувач або версія гри",
    "{0} needs {1} {2} (this instance has {3})": "{0} потребує {1} {2} (у цьому екземплярі {3})",
    "...and {0} more": "...і ще {0}",
    "{0} disabled mods": "Вимкнених модів: {0}",
    "Restore all": "Повернути всі",
    "No problems found.": "Проблем не знайдено.",
    "Keep {0} - disable {1}": "Залишити {0} - вимкнути {1}",
    "Move {0} old copies to the disabled_mods folder? Nothing is deleted.":
        "Перенести старі копії ({0}) до папки disabled_mods? Нічого не видаляється.",
    "Couldn't move some files": "Не вдалося перенести деякі файли",
    "Not restored (a mod with that name is already there):\n{0}":
        "Не повернено (мод з такою назвою вже є):\n{0}",
    "Import world into {0}": "Імпорт світу до {0}",
    "Looking for worlds...": "Пошук світів...",
    "No worlds found. Use \"Browse folder...\" to point at the folder that contains them.":
        "Світів не знайдено. Натисніть «Вибрати папку...» і вкажіть папку, де вони лежать.",
    "{0} worlds found - pick one to copy:": "Знайдено світів: {0}. Виберіть, який скопіювати:",
    "Minecraft {0}": "Minecraft {0}",
    "saved {0}": "збережено {0}",
    "Saved in a newer Minecraft version ({0}) - may not load":
        "Збережено в новішій версії Minecraft ({0}) - може не відкритися",
    "Browse folder...": "Вибрати папку...",
    "Choose a folder that contains worlds": "Виберіть папку зі світами",
    "Import": "Імпортувати",
    "Copying world... {0}%": "Копіювання світу... {0}%",
    "World imported": "Світ імпортовано",
    "'{0}' was copied into {1}. The original was not touched.":
        "«{0}» скопійовано до {1}. Оригінал не зачеплено.",

    # --- mod updater
    "Check for updates": "Оновлення модів",
    "Mod updates: {0}": "Оновлення модів: {0}",
    "Reading mods...": "Читання модів...",
    "Asking Modrinth...": "Запит до Modrinth...",
    "Asking CurseForge...": "Запит до CurseForge...",
    "Mods are tested together in a pack. Update a few at a time and test the game. Undo puts the previous versions back.":
        "Моди в збірці перевірено разом. Оновлюйте по кілька штук і перевіряйте гру. «Скасувати» поверне попередні версії.",
    "Couldn't check for updates: {0}": "Не вдалося перевірити оновлення: {0}",
    "{0} updates found, {1} up to date, {2} not recognized":
        "Знайдено оновлень: {0}, актуальних: {1}, не розпізнано: {2}",
    "Some lookups failed: {0}": "Частина запитів не вдалася: {0}",
    "Everything recognized is up to date.": "Усе розпізнане вже актуальне.",
    "download it manually": "завантажте вручну",
    "Update selected": "Оновити вибрані",
    "Updating...": "Оновлення...",
    "Updated {0} mods.": "Оновлено модів: {0}.",
    "Not updated:": "Не оновлено:",
    "Updates": "Оновлення",
    "Undo last update": "Скасувати останнє оновлення",
    "Put the previous versions of the last updated mods back?": "Повернути попередні версії модів, оновлених минулого разу?",
    "Restored {0} mods.": "Відновлено модів: {0}.",
    "Select all stable": "Вибрати всі стабільні",
    "Select none": "Зняти вибір",

    # --- change version / duplicate
    "Change version...": "Змінити версію...",
    "Duplicate...": "Дублювати...",
    "Change version: {0}": "Зміна версії: {0}",
    "Now: Minecraft {0}{1}": "Зараз: Minecraft {0}{1}",
    "Move to Minecraft:": "Перейти на Minecraft:",
    "Loading versions...": "Завантаження версій...",
    "Check": "Перевірити",
    "Pick a version and press Check. Nothing is changed by checking.":
        "Виберіть версію та натисніть «Перевірити». Перевірка нічого не змінює.",
    "Couldn't load the version list. Check your connection.": "Не вдалося завантажити список версій. Перевірте підключення.",
    "Back up my worlds first": "Спочатку зробити копію моїх світів",
    "Back up my worlds first ({0})": "Спочатку зробити копію моїх світів ({0})",
    "Backing up worlds... {0}%": "Копіювання світів... {0}%",
    "Saving a rollback snapshot...": "Збереження точки відкату...",
    "Backing up worlds...": "Копіювання світів...",
    "Downloading new builds...": "Завантаження нових версій...",
    "Applying...": "Застосування...",
    "{0} mods: {1} fit as they are, {2} will be replaced, {3} have no build for {4}, {5} not recognized":
        "Модів: {0}. Підходять як є: {1}, буде замінено: {2}, немає версії для {4}: {3}, не розпізнано: {5}",
    "Loader will be: {0}": "Завантажувач буде: {0}",
    "This pack probably can't be moved: {0} of {1} mods have nothing for Minecraft {2}.":
        "Цю збірку, найімовірніше, не можна перенести: для {0} із {1} модів немає версії під Minecraft {2}.",
    "No build for {0} - these would be moved out of the mods folder (not deleted):":
        "Немає версії для {0} - ці моди буде перенесено з папки mods (не видалено):",
    "{0} replacements are beta builds:": "Бета-версій серед замін: {0}",
    "Not recognized, left as they are (may not work):": "Не розпізнано, залишено як є (можуть не працювати):",
    "Lookup problem: {0}": "Проблема під час пошуку: {0}",
    "I understand this pack may not work, change it anyway": "Я розумію, що збірка може не працювати, усе одно змінити",
    "Change version": "Змінити версію",
    "Change {0} to Minecraft {1}?": "Перевести «{0}» на Minecraft {1}?",
    "{0} mods replaced, {1} moved out of the mods folder (nothing is deleted). You can undo this afterwards.":
        "Замінено модів: {0}, перенесено з папки mods: {1} (нічого не видаляється). Потім це можна скасувати.",
    "If something was half-changed, open Change version again and use Undo.":
        "Якщо щось змінилося частково, знову відкрийте «Змінити версію» і натисніть «Скасувати».",
    "Now on Minecraft {0}. {1} mods replaced, {2} moved out.": "Тепер Minecraft {0}. Замінено модів: {1}, перенесено: {2}.",
    "Rollback snapshot: {0}": "Точка відкату: {0}",
    "Worlds backup: {0}": "Копія світів: {0}",
    "Undo last version change": "Скасувати останню зміну версії",
    "Put back the previous version, mods and configs? Worlds are not touched.":
        "Повернути попередню версію, моди та налаштування? Світи не зачіпаються.",
    "A worlds backup from before the change is still at: {0}": "Копія світів до зміни версії залишилась тут: {0}",
    "Duplicate: {0}": "Дублювання: {0}",
    "Name of the copy:": "Назва копії:",
    "Copies everything, worlds included. Calculating size...": "Копіюється все, разом зі світами. Підрахунок розміру...",
    "Copies everything, worlds included: about {0} MB.": "Копіюється все, разом зі світами: близько {0} МБ.",
    "Copying... {0}%": "Копіювання... {0}%",
    "Duplicate": "Дублювати",
    "'{0}' was created.": "«{0}» створено.",
    "Mods with no build for this version:": "Моди без версії під цей Minecraft:",
    "Move them out of the mods folder (recommended, Undo brings them back)":
        "Перенести з папки mods (рекомендовано, «Скасувати» поверне їх)",
    "Keep them in anyway (some still work, others can stop the game starting)":
        "Залишити все одно (частина працює, але інші можуть завадити запуску гри)",
    "{0} mods replaced. {1} mods with no build stay in the mods folder - they may stop the game from starting. You can undo this afterwards.":
        "Замінено модів: {0}. Моди без відповідної версії ({1}) залишаються в папці mods і можуть завадити запуску гри. Потім це можна скасувати.",
    "Kept in the mods folder anyway: {0}": "Залишено в папці mods: {0}",
    "No build for {0}:": "Немає версії для {0}:",
    # --- redesign
    "Choose how to sign in": "Виберіть спосіб входу",
    "Healthy": "Усе гаразд",
    "{0} duplicate mods": "Дублікатів модів: {0}",
    "Needs a newer loader": "Потрібен новіший завантажувач",
    "Fix problems": "Виправити",
    "{0} duplicates": "Дублікатів: {0}",
    "Loader too old": "Завантажувач застарів",
    "Older copy": "Стара копія",
    "Needs {0} {1}": "Потрібен {0} {1}",
    "{0} off": "вимк.: {0}",
    "Couldn't change the mod": "Не вдалося змінити мод",
    # --- world backups / sharing
    "World backups...": "Копії світів...",
    "Back up worlds before launching": "Копіювати світи перед запуском",
    "World backups: {0}": "Резервні копії світів: {0}",
    "World backups": "Резервні копії світів",
    "Backups are saved in the instance folder. Restoring keeps the current world under a new name, nothing is deleted. Close Minecraft before restoring.":
        "Копії зберігаються в папці екземпляра. Під час відновлення поточний світ зберігається під новою назвою, нічого не видаляється. Перед відновленням закрийте Minecraft.",
    "No backups yet. One is made automatically when you press Play, after a world has changed.":
        "Копій поки немає. Копія створюється автоматично під час натискання «Грати», якщо світ змінився.",
    "Back up now": "Створити копію",
    "Open backups folder": "Відкрити папку копій",
    "Restore": "Відновити",
    "Backup done: {0} new, {1} unchanged.": "Готово: нових копій — {0}, без змін — {1}.",
    "Backup failed": "Не вдалося створити копію",
    "Restore '{0}' from {1}?\n\nThe current version of this world is kept under a new name.":
        "Відновити «{0}» з копії від {1}?\n\nПоточна версія світу збережеться під новою назвою.",
    "Restored. The previous version was kept as '{0}'.": "Готово. Попередню версію збережено як «{0}».",
    "Restored.": "Готово.",
    "Restore failed": "Не вдалося відновити",
    "Copy for sharing": "Копія для надсилання",
    # --- duplicate fixer now deletes
    "Keeps the newest of each and deletes the older copies.": "Залишає найновішу копію кожного мода, а старі видаляє.",
    "Keep {0} - delete {1}": "Залишити {0} - видалити {1}",
    "Delete {0} old copies? This can't be undone.": "Видалити старі копії ({0})? Це неможливо скасувати.",
    "Couldn't delete some files": "Не вдалося видалити деякі файли",
    # --- settings: CurseForge key
    'CurseForge API key (optional):': "Ключ API CurseForge (необов'язково):",
    'Save': 'Зберегти',
    'Using your own key.': 'Використовується ваш ключ.',
    'Using the built-in key.': 'Використовується вбудований ключ.',
    "That doesn't look like a CurseForge key.": 'Це не схоже на ключ CurseForge.',
    'Key saved.': 'Ключ збережено.',
    'Your key was removed.': 'Ваш ключ видалено.',
    'Leave it empty to use the built-in key. You can get a free key at console.curseforge.com.': 'Залиште поле порожнім, щоб використовувати вбудований ключ. Безкоштовний ключ можна отримати на console.curseforge.com.',
    # --- delete leftovers in disabled_mods
    'Delete all': 'Видалити всі',
    "Permanently delete {0} switched-off mods? This includes mods you switched off yourself, and it can't be undone.": 'Видалити назавжди вимкнені моди ({0})? Серед них можуть бути моди, які ви вимкнули самі. Скасувати це неможливо.',
    # --- crash helper: suspected mod
    'Suspected mod: {0}': 'Підозрілий мод: {0}',
    'Disable this mod': 'Вимкнути цей мод',
    'Disabled': 'Вимкнено',
    "Couldn't disable it: {0}": 'Не вдалося вимкнути: {0}',
    '{0} is switched off. Press Play to try again; you can switch it back on in Manage.': '{0} вимкнено. Натисніть «Грати», щоб спробувати ще раз; увімкнути його знову можна в «Керування».',
    # --- mod list: turned-off section
    'Turned off ({0})': 'Вимкнені ({0})',
}
