param(
    [switch]$Force,
    [switch]$Install,
    [switch]$SkipTests,
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$cfg = Get-Content (Join-Path $root "build.config.json") -Encoding UTF8 | ConvertFrom-Json
if (-not $Version) { $Version = $cfg.version }
$py = $cfg.python
$env:PYTHONIOENCODING = "utf-8"

function Step([string]$title) {
    Write-Host ""
    Write-Host "=== $title ===" -ForegroundColor Cyan
}

function Invoke-Python([string[]]$arguments) {
    & $py -X utf8 @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python step failed: $($arguments -join ' ')"
    }
}

Set-Location $root

# 0. Guard against replacing a DLL that the running game has loaded.
$game = Get-Process Arknights -ErrorAction SilentlyContinue
if ($game) {
    throw "Arknights.exe is running. Close the game before building/installing."
}

Step "1/8 Import operator glossary"
Invoke-Python @("tools/import_glossary.py")

Step "2/8 Build story speaker names"
Invoke-Python @("tools/build_story_names.py")

Step "3/8 Merge RU translation map"
$mergeArgs = @("tools/build_ru_merged_pack.py")
if ($Force) { $mergeArgs += "--force" }
Invoke-Python $mergeArgs

Step "4/8 Expand skill/module direct translations"
Invoke-Python @("tools/build_skill_direct.py")

Step "5/8 Build dynamic macro templates"
Invoke-Python @("tools/build_dynamic_templates.py")

Step "6/8 Build XUnity text pack"
if (Test-Path (Join-Path $root $cfg.packOutput)) {
    Remove-Item (Join-Path $root $cfg.packOutput) -Recurse -Force
}
Invoke-Python @(
    "-m", "arklocalizer.cli", "build-custom-pack",
    "--manifests", $cfg.manifests,
    "--output", $cfg.packOutput
)
# 14_regex.txt is intentionally not shipped: the plugin handles macro
# templates, and a huge regex file causes a minute-long first-load freeze.
$regexPack = Join-Path $root (Join-Path $cfg.packOutput "Translation/ru/Text/14_regex.txt")
if (Test-Path $regexPack) { Remove-Item $regexPack -Force }

Step "7/8 Build RichTextFix plugin and RU context"
Invoke-Python @("tools/build_ru_context_merged.py")
& dotnet build $cfg.pluginProject -c Release --nologo "-p:GameInteropPath=$($cfg.gameInterop)"
if ($LASTEXITCODE -ne 0) { throw "dotnet build failed" }
if (-not (Test-Path $cfg.pluginDll)) { throw "plugin DLL not found: $($cfg.pluginDll)" }

Step "8/8 Package release v$Version"
Invoke-Python @("tools/package_merged_hook.py", "--version", $Version)

if (-not $SkipTests) {
    Step "Contract tests"
    Invoke-Python @("tools/contract_test.py")
}

if ($Install) {
    Step "Install into game"
    $textDir = Join-Path $cfg.game "BepInEx/Translation/ru/Text"
    $pluginDir = Join-Path $cfg.game "BepInEx/plugins/ArknightsLocalization"
    $configDir = Join-Path $cfg.game "BepInEx/config"
    New-Item -ItemType Directory -Force -Path $textDir, $pluginDir, $configDir | Out-Null

    foreach ($name in @("11_ui.txt", "12_story.txt", "13_names.txt")) {
        Copy-Item (Join-Path $root (Join-Path $cfg.packOutput "Translation/ru/Text/$name")) $textDir -Force
    }
    # Remove the obsolete regex pack from previous versions.
    $oldRegex = Join-Path $textDir "14_regex.txt"
    if (Test-Path $oldRegex) { Remove-Item $oldRegex -Force }

    Copy-Item (Join-Path $root $cfg.configFile) $configDir -Force
    Copy-Item $cfg.pluginDll $pluginDir -Force
    Copy-Item (Join-Path $root $cfg.fontFile) $pluginDir -Force
    # Replacement RU faces: the plugin loads the bundle from the plugin folder
    # first and from the game root as a fallback for old launcher layouts.
    $fontBundle = Join-Path $root "runtime/en-zh-offline-final/arknights_cn_notosanshans"
    Copy-Item $fontBundle $pluginDir -Force
    Copy-Item $fontBundle $cfg.game -Force
    Write-Host "Installed v$Version into $($cfg.game)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Build complete: v$Version" -ForegroundColor Green
