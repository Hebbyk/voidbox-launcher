# Voidbox Launcher

**English** | [Русский](README.ru.md)

A free, lightweight Minecraft launcher built around modpacks: drag in a pack, press Play. No ads, no tracking.

## Download

1. Go to the [latest release](https://github.com/Hebbyk/voidbox-launcher/releases/latest).
2. Download the `.msi` installer and run it.

Windows only for now.

> **SmartScreen warning:** the installer isn't code-signed yet, so Windows may show "Windows protected your PC". Click **More info → Run anyway**.

## What it does

**Packs and Java**
- **Imports the three big modpack formats**: Modrinth (`.mrpack`), CurseForge (`.zip`) and Packwiz (`pack.toml`), including remote index files for auto-updating packs.
- **Handles Java for you**: picks the Java version each Minecraft version needs and downloads it if it's missing.

**Looking after an instance**
- **Mod health check**: finds duplicate mods by reading each jar's real ID and version, moves the older copy to a `disabled_mods` folder (nothing is deleted), and warns when a mod needs a newer NeoForge than the instance has.
- **Mod updater**: identifies every mod by its file hash on Modrinth (and CurseForge, with an API key), updates only the ones you tick, and keeps the old file so **Undo** can put it back. Betas are never pre-selected.
- **Change version**: moves an instance to another Minecraft version in place, with a rollback snapshot and an optional backup of your worlds. It works best for packs made of ordinary mods; a pack built around its own custom mods usually can't move until its author ports it.
- **Switch mods on and off** without deleting them.
- **Import worlds** from the CurseForge app, the official launcher or any folder. Worlds are copied, never moved.
- **Duplicate an instance**, worlds included.
- **Crash helper**: if the game closes with an error, the launcher shows the real error lines from the log, with Copy and Open-folder buttons.

**The basics**
- **English and Russian interface.**
- **Microsoft and ely.by sign-in.**
- **Update checks** through GitHub Releases.
- **No ads, no tracking.**

## Community

Questions, bug reports and ideas are welcome on the [Discord server](https://discord.gg/xH3Rg4vKNb). English and Russian are both fine.

## Something went wrong?

Ask in `#help` on [Discord](https://discord.gg/xH3Rg4vKNb) or open an [Issue](https://github.com/Hebbyk/voidbox-launcher/issues), and attach the game log. Paste this path into the Explorer address bar:

```
%LOCALAPPDATA%\MCLauncher\instances\<instance name>\minecraft\logs\latest.log
```

## Open source

Voidbox Launcher is free software, released under the [GNU GPL v3](LICENSE). Copyright (c) 2026 Hebby. You can read it, change it and share it, as long as your version stays under the GPL, keeps the copyright notice and publishes its source.

**Run from source** (Windows, Python 3, normal non-admin terminal):

```
py -m pip install -r requirements.txt
py gui.py
```

**Build the installer** (needs the .NET SDK and WiX):

```
.\build.ps1 -Version 1.2.3
```

The MSI ends up in `dist\`.

**CurseForge key:** the source contains no API key. The launcher asks for one when you import a CurseForge pack (you can get a free key at [console.curseforge.com](https://console.curseforge.com)). To bake your own key into your build, run `py make_key.py` before building.

## Contributing

Bug reports, ideas and pull requests are welcome: open an [Issue](https://github.com/Hebbyk/voidbox-launcher/issues) or talk to us on [Discord](https://discord.gg/xH3Rg4vKNb).

## Built with

Python and CustomTkinter.

<!-- Add a screenshot here: ![Voidbox Launcher](docs/screenshot.png) -->
