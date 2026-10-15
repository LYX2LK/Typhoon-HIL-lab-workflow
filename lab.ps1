[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$LabArguments)
$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$typhoonInstall = $env:TYPHOON_HOME
$configFile = Join-Path $projectRoot "environment.local.json"
if (-not $typhoonInstall -and (Test-Path -LiteralPath $configFile)) {
    $settings = Get-Content -LiteralPath $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $typhoonInstall = $settings.typhoon_home
}
if (-not $typhoonInstall) {
    $candidates = @(Get-ChildItem -LiteralPath (Split-Path $projectRoot -Parent) -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "python3_portable\python.exe") })
    if ($candidates.Count -eq 1) { $typhoonInstall = $candidates[0].FullName }
}
if (-not $typhoonInstall) { throw "Set TYPHOON_HOME or environment.local.json typhoon_home." }
$pythonExecutable = Join-Path $typhoonInstall "python3_portable\python.exe"
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw "Bundled Python not found: $pythonExecutable" }
$env:TYPHOON_LAB_INSTALL = $typhoonInstall
& $pythonExecutable -B -X utf8 (Join-Path $projectRoot "scripts\lab_cli.py") @LabArguments
exit $LASTEXITCODE
