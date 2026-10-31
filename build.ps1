# Builds Voidbox Launcher: PyInstaller folder -> MSI.
# Usage (PowerShell, from this folder):  .\build.ps1                    (reuse the version in version.py)
#                                        .\build.ps1 -Version 1.0.1     (set a new version, then build)
param([string]$Version = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

foreach ($f in "gui.py", "core.py", "icon.ico", "theme_violet_nebula.json", "version.py", "i18n.py", "lang_ru.py", "voidbox.spec", "voidbox.wxs", "LICENSE", "NOTICE") {
    if (-not (Test-Path $f)) { throw "Missing $f in $PSScriptRoot" }
}

if (-not (Test-Path "_cfk.py")) {
    Write-Host "NOTE: _cfk.py not found - this build will have no built-in CurseForge key (run: py make_key.py)" -ForegroundColor Yellow
}

# One version number for everything: version.py is shown in the app, drives the update check,
# and names the MSI. "-Version 1.0.1" sets it; with no argument the current one is reused.
if ($Version) { Set-Content version.py "APP_VERSION = `"$Version`"" -Encoding ascii }
else { $Version = [regex]::Match((Get-Content version.py -Raw), 'APP_VERSION\s*=\s*"([^"]+)"').Groups[1].Value }
if (-not $Version) { throw "Couldn't read APP_VERSION from version.py" }
Write-Host "Building version $Version" -ForegroundColor Cyan

# Per-version build tag.
if (Test-Path canary.py) {
    py canary.py ensure $Version
    if ($LASTEXITCODE -ne 0) { throw "canary.py failed" }
}

Write-Host "== 1/2  PyInstaller ==" -ForegroundColor Cyan

# A still-running copy of the app (or an Explorer/terminal window sitting in dist\VoidboxLauncher)
# locks that folder, and PyInstaller then dies trying to clear it. Close the app, clear it ourselves.
Get-Process -Name "Voidbox Launcher" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500
if (Test-Path "dist\VoidboxLauncher") {
    try { Remove-Item "dist\VoidboxLauncher" -Recurse -Force -ErrorAction Stop }
    catch { throw "Can't clear dist\VoidboxLauncher - something is still using it. Close Voidbox Launcher and any Explorer window or terminal that is inside that folder, then run again." }
}
py -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" }
py -m PyInstaller voidbox.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
$appMb = [math]::Round((Get-ChildItem "dist\VoidboxLauncher" -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "App folder ready ($appMb MB): dist\VoidboxLauncher\Voidbox Launcher.exe  (test it before the MSI step)" -ForegroundColor Green

Write-Host "== 2/2  MSI (WiX) ==" -ForegroundColor Cyan
if (-not (Get-Command wix -ErrorAction SilentlyContinue)) {
    Write-Host "WiX not found, so no MSI was built. One-time setup:" -ForegroundColor Yellow
    Write-Host "    winget install Microsoft.DotNet.SDK.8"
    Write-Host "    dotnet tool install --global wix"
    Write-Host "Then open a NEW PowerShell and run .\build.ps1 again."
    exit 0
}
# The setup wizard (options page) comes from WiX's UI extension; installed once per machine.
$uiExt = "WixToolset.UI.wixext"
$wixVer = [regex]::Match((wix --version | Out-String), '\d+\.\d+\.\d+').Value
if (-not ((wix extension list -g | Out-String) -match [regex]::Escape($uiExt))) {
    Write-Host "Installing the WiX UI extension ($uiExt $wixVer)..."
    if ($wixVer) { wix extension add -g "$uiExt/$wixVer" } else { wix extension add -g $uiExt }
    if ($LASTEXITCODE -ne 0) { throw "Couldn't install the WiX UI extension" }
}
New-Item -ItemType Directory -Force dist | Out-Null
# Delete old installers first: if this build fails, you must not be able to run a stale MSI by mistake.
Get-ChildItem dist\*.msi -ErrorAction SilentlyContinue | Remove-Item -Force
$msi = "dist\Voidbox-Launcher-$Version.msi"
wix build voidbox.wxs -ext $uiExt -arch x64 -d Version=$Version -o $msi
if ($LASTEXITCODE -ne 0) { throw "wix build failed" }
$msiMb = [math]::Round((Get-Item $msi).Length / 1MB)
Write-Host "Built $((Resolve-Path $msi).Path) ($msiMb MB) at $((Get-Item $msi).LastWriteTime)" -ForegroundColor Green
