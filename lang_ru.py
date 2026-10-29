"""
mc_launcher.lang_ru — Russian translations (English text -> Russian).

The key is the exact English text passed to tr(); {0}, {1}, ... are placeholders
and must appear in the translation too (the order may differ). A missing entry just
shows in English. Terminology: instance = экземпляр, modpack = сборка, mod = мод,
loader = загрузчик, "premium" = лицензия. ely.by is always written as "ely.by".
"""

RU = {
    # --- sidebar / accounts
    "Account": "Аккаунт",
    "Not logged in": "Вход не выполнен",
    "Login (ely.by)": "Вход (ely.by)",
    "Login (Microsoft)": "Вход (Microsoft)",
    "Logged in:\n{0} (ely.by)": "Вы вошли как:\n{0} (ely.by)",
    "Logged in:\n{0} (premium)": "Вы вошли как:\n{0} (лицензия)",
    "Logging in with Microsoft...": "Вход через Microsoft...",
    "Login failed": "Ошибка входа",
    "ely.by username:": "Имя пользователя ely.by:",
    "ely.by password:": "Пароль ely.by:",
    "Log in (ely.by or Microsoft) first.": "Сначала выполните вход (ely.by или Microsoft).",
    "+ Add Instance": "+ Добавить экземпляр",
    "Refresh": "Обновить",
    "Output": "Вывод",

    # --- tabs / lists / search
    "Instances": "Экземпляры",
    "Browse": "Обзор",
    "Your Instances": "Ваши экземпляры",
    "Results": "Результаты",
    "Search instances (name, loader, version)...": "Поиск экземпляров (название, загрузчик, версия)...",
    "Search modpacks...": "Поиск сборок...",
    "Search mods...": "Поиск модов...",
    "Search": "Поиск",
    "Search failed": "Ошибка поиска",
    "Searching for '{0}'...": "Поиск «{0}»...",
    "No results.": "Ничего не найдено.",
    "No instances yet — click + Add Instance": "Экземпляров пока нет — нажмите «+ Добавить экземпляр»",
    "No instances match \"{0}\"": "Нет экземпляров, подходящих под «{0}»",
    "Adding mods to: {0}  ({1} on Minecraft {2})": "Добавление модов в: {0}  ({1} на Minecraft {2})",
    "Cancel": "Отмена",
    "← Back to results": "← Назад к результатам",
    "Loading details...": "Загрузка сведений...",
    "Couldn't load full details ({0}) — showing what search already had.":
        "Не удалось загрузить полные сведения ({0}) — показано то, что уже было в результатах поиска.",
    "Latest changelog:": "Последние изменения:",

    # --- instance rows / actions
    "Play": "Играть",
    "Export": "Экспорт",
    "Delete": "Удалить",
    "Launching {0}...": "Запуск {0}...",
    "Launch failed": "Не удалось запустить",
    "Delete instance": "Удаление экземпляра",
    "Delete '{0}'? This also deletes its files (mods, saves, etc.).":
        "Удалить «{0}»? Его файлы (моды, сохранения и т. д.) тоже будут удалены.",
    "Some files couldn't be deleted": "Не удалось удалить некоторые файлы",
    "'{0}' was removed from the list, but {1} file(s) couldn't be deleted — probably still in use (close Minecraft/Java first if it's running):\n\n{2}":
        "«{0}» удалён из списка, но не удалось удалить файлы ({1}) — вероятно, они используются (если Minecraft запущен, сначала закройте Minecraft/Java):\n\n{2}",

    # --- add instance / import
    "Add Instance": "Добавить экземпляр",
    "Instance name:": "Название экземпляра:",
    "Minecraft version (e.g. 1.20.1):": "Версия Minecraft (например, 1.20.1):",
    "Loader:": "Загрузчик:",
    "Create Blank Instance": "Создать пустой экземпляр",
    "Import from Pack File (.mrpack / .zip)": "Импорт из файла сборки (.mrpack / .zip)",
    "Missing info": "Не хватает данных",
    "Enter a name and Minecraft version.": "Введите название и версию Minecraft.",
    "Enter a name first.": "Сначала введите название.",
    "Select a modpack file": "Выберите файл сборки",
    "Modpack files": "Файлы сборок",
    "All files": "Все файлы",
    "CurseForge API Key": "Ключ API CurseForge",
    "This looks like a CurseForge pack — paste your API key:":
        "Похоже, это сборка CurseForge — вставьте свой ключ API:",
    "Importing {0}...": "Импорт {0}...",
    "Importing {0}... ({1}/{2})": "Импорт {0}... ({1}/{2})",
    "'{0}' imported successfully.": "«{0}» успешно импортирован.",
    "Import failed": "Ошибка импорта",
    "Done": "Готово",

    # --- install from search
    "Install: {0}": "Установка: {0}",
    "Install": "Установить",
    "Version:": "Версия:",
    "Loading...": "Загрузка...",
    "No versions found": "Версии не найдены",
    "Couldn't load versions": "Не удалось загрузить версии",
    "Enter a name and wait for versions to load.": "Введите название и дождитесь загрузки версий.",
    "Pick a version": "Выберите версию",
    "Select a version first.": "Сначала выберите версию.",
    "Downloading {0}...": "Загрузка {0}...",
    "Installing {0}...": "Установка {0}...",
    "Installing {0}... ({1}/{2})": "Установка {0}... ({1}/{2})",
    "'{0}' installed successfully.": "«{0}» успешно установлен.",
    "Install failed": "Ошибка установки",

    # --- manage instance / add mods
    "Manage: {0}": "Управление: {0}",
    "Change Icon...": "Сменить значок...",
    "Choose an icon image": "Выберите изображение значка",
    "Images": "Изображения",
    "Couldn't set icon": "Не удалось установить значок",
    "Rename": "Переименовать",
    "Rename failed": "Не удалось переименовать",
    "Open Instance Folder": "Открыть папку экземпляра",
    "Couldn't open folder": "Не удалось открыть папку",
    "Add Mods...": "Добавить моды...",
    "Mods": "Моды",
    "Mods ({0})": "Моды ({0})",
    "No mods in this instance.": "В этом экземпляре нет модов.",
    "Remove": "Удалить",
    "Remove mod": "Удаление мода",
    "Delete '{0}' from {1}?": "Удалить «{0}» из {1}?",
    "Couldn't remove mod": "Не удалось удалить мод",
    "{0}\n\n(If Minecraft is running, close it and try again.)":
        "{0}\n\n(Если Minecraft запущен, закройте его и повторите попытку.)",
    "Add to {0}: {1}": "Добавить в {0}: {1}",
    "Compatible builds for {0} {1}:": "Совместимые версии для {0} {1}:",
    "No build of '{0}' found for {1} {2}.": "Для {1} {2} не найдена версия «{0}».",
    "Couldn't load builds": "Не удалось загрузить версии",
    "Pick a build": "Выберите версию",
    "Select a build first.": "Сначала выберите версию.",
    "Add to Instance": "Добавить в экземпляр",
    "Adding...": "Добавление...",
    "Downloading...": "Загрузка...",
    "Downloading... {0}%": "Загрузка... {0}%",
    "Added": "Добавлено",
    "'{0}' added to {1}.": "«{0}» добавлен в {1}.",
    "Add failed": "Не удалось добавить",

    # --- export
    "Export: {0}": "Экспорт: {0}",
    "Format:": "Формат:",
    "Save to:": "Сохранить в:",
    "(not chosen)": "(не выбрано)",
    "Browse...": "Обзор...",
    "Choose export folder": "Выберите папку для экспорта",
    "Choose export file": "Выберите файл для экспорта",
    "Choose where to save first.": "Сначала выберите, куда сохранить.",
    "Exporting...": "Экспорт...",
    "Exporting... {0}%": "Экспорт... {0}%",
    "Exported to:\n{0}": "Экспортировано в:\n{0}",
    "Export failed": "Ошибка экспорта",

    # --- updates
    "Voidbox Launcher {0} is available (you have {1}).": "Доступна версия Voidbox Launcher {0} (у вас {1}).",
    "Update now": "Обновить сейчас",
    "Later": "Позже",
    "Downloading {0}... {1}%": "Загрузка {0}... {1}%",
    "Installer opened. Closing Voidbox Launcher so it can update...":
        "Установщик открыт. Voidbox Launcher закрывается, чтобы обновиться...",
    "Update failed.": "Не удалось обновить.",
    "Update failed": "Ошибка обновления",

    # --- settings
    "Settings": "Настройки",
    "Language:": "Язык:",
    "Version {0}": "Версия {0}",
    "Language changed. Restart Voidbox Launcher to apply it.":
        "Язык изменён. Перезапустите Voidbox Launcher, чтобы применить его.",
    "Restart now": "Перезапустить сейчас",
    "Couldn't restart": "Не удалось перезапустить",

    # --- misc
    "Couldn't start the installer: {0}": "Не удалось запустить установщик: {0}",
    "\n\nYou can download it manually:\n{0}": "\n\nВы можете скачать его вручную:\n{0}",
    "(no description)": "(нет описания)",
    "Need a CurseForge API key to list files for this pack.":
        "Нужен ключ API CurseForge, чтобы получить список файлов этой сборки.",
    "Need a CurseForge API key to list files for this mod.":
        "Нужен ключ API CurseForge, чтобы получить список файлов этого мода.",

    # --- crash helper
    "Minecraft closed with an error (exit code {0})": "Minecraft закрылся с ошибкой (код выхода {0})",
    "It ran for {0} seconds.": "Он проработал {0} с.",
    "No new log was written, so Minecraft stopped before it could log anything. This usually means a Java or launch-argument problem.":
        "Новый лог не создан: Minecraft остановился раньше, чем успел что-либо записать. Обычно это значит, что проблема с Java или с аргументами запуска.",
    "Crash report: {0}": "Отчёт о сбое: {0}",
    "Copy log": "Копировать лог",
    "Copied!": "Скопировано!",
    "(no log was written)": "(лог не был создан)",
    "Open log folder": "Открыть папку с логами",

    # --- mod health / world import
    "Import World...": "Импорт мира...",
    "Checking mods...": "Проверка модов...",
    "Couldn't check mods: {0}": "Не удалось проверить моды: {0}",
    "{0} mods have an old extra copy": "У модов с лишней старой копией: {0}",
    "Keeps the newest of each and moves the rest to the disabled_mods folder. Nothing is deleted.":
        "Оставляет самую новую версию каждого мода, а остальные переносит в папку disabled_mods. Ничего не удаляется.",
    "Fix duplicates": "Исправить дубликаты",
    "{0} need a manual look": "Требуют ручной проверки: {0}",
    "These also provide other mods, so they were left alone: {0}":
        "Они содержат и другие моды, поэтому их не тронули: {0}",
    "Needs a newer loader or game version": "Нужен более новый загрузчик или версия игры",
    "{0} needs {1} {2} (this instance has {3})": "{0} требует {1} {2} (в этом экземпляре {3})",
    "...and {0} more": "...и ещё {0}",
    "{0} disabled mods": "Отключённых модов: {0}",
    "Restore all": "Вернуть все",
    "No problems found.": "Проблем не найдено.",
    "Keep {0} - disable {1}": "Оставить {0} - отключить {1}",
    "Move {0} old copies to the disabled_mods folder? Nothing is deleted.":
        "Перенести старые копии ({0}) в папку disabled_mods? Ничего не удаляется.",
    "Couldn't move some files": "Не удалось перенести некоторые файлы",
    "Not restored (a mod with that name is already there):\n{0}":
        "Не возвращены (мод с таким именем уже есть):\n{0}",
    "Import world into {0}": "Импорт мира в {0}",
    "Looking for worlds...": "Поиск миров...",
    "No worlds found. Use \"Browse folder...\" to point at the folder that contains them.":
        "Миры не найдены. Нажмите «Выбрать папку...» и укажите папку, где они лежат.",
    "{0} worlds found - pick one to copy:": "Найдено миров: {0}. Выберите, какой скопировать:",
    "Minecraft {0}": "Minecraft {0}",
    "saved {0}": "сохранён {0}",
    "Saved in a newer Minecraft version ({0}) - may not load":
        "Сохранён в более новой версии Minecraft ({0}) - может не открыться",
    "Browse folder...": "Выбрать папку...",
    "Choose a folder that contains worlds": "Выберите папку с мирами",
    "Import": "Импортировать",
    "Copying world... {0}%": "Копирование мира... {0}%",
    "World imported": "Мир импортирован",
    "'{0}' was copied into {1}. The original was not touched.":
        "«{0}» скопирован в {1}. Оригинал не тронут.",

    # --- mod updater
    "Check for updates": "Проверить обновления",
    "Mod updates: {0}": "Обновления модов: {0}",
    "Reading mods...": "Чтение модов...",
    "Asking Modrinth...": "Запрос к Modrinth...",
    "Asking CurseForge...": "Запрос к CurseForge...",
    "Mods are tested together in a pack. Update a few at a time and test the game. Undo puts the previous versions back.":
        "Моды в сборке проверены вместе. Обновляйте по несколько штук и проверяйте игру. «Отменить» вернёт прежние версии.",
    "Couldn't check for updates: {0}": "Не удалось проверить обновления: {0}",
    "{0} updates found, {1} up to date, {2} not recognized":
        "Найдено обновлений: {0}, актуальных: {1}, не распознано: {2}",
    "Some lookups failed: {0}": "Часть запросов не удалась: {0}",
    "Everything recognized is up to date.": "Всё распознанное уже актуально.",
    "download it manually": "скачайте вручную",
    "Update selected": "Обновить выбранные",
    "Update failed": "Ошибка обновления",
    "Updating...": "Обновление...",
    "Updated {0} mods.": "Обновлено модов: {0}.",
    "Not updated:": "Не обновлено:",
    "Updates": "Обновления",
    "Undo last update": "Отменить последнее обновление",
    "Put the previous versions of the last updated mods back?": "Вернуть прежние версии модов, обновлённых в прошлый раз?",
    "Restored {0} mods.": "Восстановлено модов: {0}.",
    "Select all stable": "Выбрать все стабильные",
    "Select none": "Снять выбор",

    # --- change version / duplicate
    "Change version...": "Сменить версию...",
    "Duplicate...": "Дублировать...",
    "Change version: {0}": "Смена версии: {0}",
    "Now: Minecraft {0}{1}": "Сейчас: Minecraft {0}{1}",
    "Move to Minecraft:": "Перейти на Minecraft:",
    "Loading versions...": "Загрузка версий...",
    "Check": "Проверить",
    "Pick a version and press Check. Nothing is changed by checking.":
        "Выберите версию и нажмите «Проверить». Проверка ничего не меняет.",
    "Couldn't load the version list. Check your connection.": "Не удалось загрузить список версий. Проверьте подключение.",
    "Back up my worlds first": "Сначала сделать копию моих миров",
    "Back up my worlds first ({0})": "Сначала сделать копию моих миров ({0})",
    "Backing up worlds... {0}%": "Копирование миров... {0}%",
    "Saving a rollback snapshot...": "Сохранение точки отката...",
    "Backing up worlds...": "Копирование миров...",
    "Downloading new builds...": "Загрузка новых версий...",
    "Applying...": "Применение...",
    "{0} mods: {1} fit as they are, {2} will be replaced, {3} have no build for {4}, {5} not recognized":
        "Модов: {0}. Подходят как есть: {1}, будут заменены: {2}, нет версии для {4}: {3}, не распознано: {5}",
    "Loader will be: {0}": "Загрузчик будет: {0}",
    "This pack probably can't be moved: {0} of {1} mods have nothing for Minecraft {2}.":
        "Эту сборку, скорее всего, нельзя перенести: для {0} из {1} модов нет версии под Minecraft {2}.",
    "No build for {0} - these would be moved out of the mods folder (not deleted):":
        "Нет версии для {0} - эти моды будут перенесены из папки mods (не удалены):",
    "{0} replacements are beta builds:": "Бета-версий среди замен: {0}",
    "Not recognized, left as they are (may not work):": "Не распознаны, оставлены как есть (могут не работать):",
    "Lookup problem: {0}": "Проблема при поиске: {0}",
    "I understand this pack may not work, change it anyway": "Я понимаю, что сборка может не работать, всё равно сменить",
    "Change version": "Сменить версию",
    "Change {0} to Minecraft {1}?": "Перевести «{0}» на Minecraft {1}?",
    "{0} mods replaced, {1} moved out of the mods folder (nothing is deleted). You can undo this afterwards.":
        "Заменено модов: {0}, перенесено из папки mods: {1} (ничего не удаляется). Потом это можно отменить.",
    "If something was half-changed, open Change version again and use Undo.":
        "Если что-то изменилось частично, снова откройте «Сменить версию» и нажмите «Отменить».",
    "Now on Minecraft {0}. {1} mods replaced, {2} moved out.": "Теперь Minecraft {0}. Заменено модов: {1}, перенесено: {2}.",
    "Rollback snapshot: {0}": "Точка отката: {0}",
    "Worlds backup: {0}": "Копия миров: {0}",
    "Undo last version change": "Отменить последнюю смену версии",
    "Put back the previous version, mods and configs? Worlds are not touched.":
        "Вернуть прежнюю версию, моды и настройки? Миры не затрагиваются.",
    "A worlds backup from before the change is still at: {0}": "Копия миров до смены версии осталась здесь: {0}",
    "Duplicate: {0}": "Дублирование: {0}",
    "Name of the copy:": "Название копии:",
    "Copies everything, worlds included. Calculating size...": "Копируется всё, включая миры. Подсчёт размера...",
    "Copies everything, worlds included: about {0} MB.": "Копируется всё, включая миры: около {0} МБ.",
    "Copying... {0}%": "Копирование... {0}%",
    "Duplicate": "Дублировать",
    "'{0}' was created.": "«{0}» создан.",
    "Mods with no build for this version:": "Моды без версии под этот Minecraft:",
    "Move them out of the mods folder (recommended, Undo brings them back)":
        "Перенести из папки mods (рекомендуется, «Отменить» вернёт их)",
    "Keep them in anyway (some still work, others can stop the game starting)":
        "Оставить всё равно (часть работает, но другие могут помешать запуску игры)",
    "{0} mods replaced. {1} mods with no build stay in the mods folder - they may stop the game from starting. You can undo this afterwards.":
        "Заменено модов: {0}. Моды без подходящей версии ({1}) остаются в папке mods и могут помешать запуску игры. Потом это можно отменить.",
    "Kept in the mods folder anyway: {0}": "Оставлено в папке mods: {0}",
    "No build for {0}:": "Нет версии для {0}:",
    # --- redesign
    "Choose how to sign in": "Выберите способ входа",
    "Healthy": "Всё в порядке",
    "{0} duplicate mods": "Дубликатов модов: {0}",
    "Needs a newer loader": "Нужен более новый загрузчик",
    "Fix problems": "Исправить",
    "{0} duplicates": "Дубликатов: {0}",
    "Loader too old": "Загрузчик устарел",
    "Older copy": "Старая копия",
    "Needs {0} {1}": "Нужен {0} {1}",
    "{0} off": "выкл.: {0}",
    "Couldn't change the mod": "Не удалось изменить мод",
}
