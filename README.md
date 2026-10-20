# Voidbox Launcher

**English** | [Русский](README.ru.md)

A free, lightweight Minecraft launcher built around modpacks: drag in a pack, press Play. No ads, no tracking.

## Download

1. Go to the [latest release](https://github.com/Hebbyk/voidbox-launcher/releases/latest).
2. Download the `.msi` installer and run it.

Windows only for now.

> **SmartScreen warning:** the installer isn't code-signed yet, so Windows may show "Windows protected your PC". Click **More info → Run anyway**.

## What it does

- **Imports the three big modpack formats**: Modrinth (`.mrpack`), CurseForge (`.zip`) and Packwiz (`pack.toml`), including remote index files for auto-updating packs.
- **Handles Java for you**: picks the Java version each Minecraft version needs and downloads it if it's missing.
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

## Built with

Python and CustomTkinter.


