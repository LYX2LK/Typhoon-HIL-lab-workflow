[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$LabArguments)
$ErrorActionPreference = "Stop"
$jsonMode = $LabArguments -contains '--json'
# Nonzero experiment exit codes are results, not PowerShell launch exceptions.
$PSNativeCommandUseErrorActionPreference = $false
try {
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
} catch {
    if (-not $jsonMode) { throw }
    $knownCommands = @('doctor','prepare-models','smoke','inspect','run','sweep','report','verify','compare-rectifier','list-cases','validate-case','run-case','practice-model')
    $selectedCommand = @($LabArguments | Where-Object { $_ -in $knownCommands }) | Select-Object -First 1
    $response = [ordered]@{
        schema_version = 1; command = $selectedCommand; status = 'error'; run_dir = $null
        record_status = $null; experiment_status = $null; artifacts = @{}; result = @{}
        error = @{ code = 'launcher_error'; stage = 'launcher'; message = $_.Exception.Message }
    }
    $response | ConvertTo-Json -Depth 20 -Compress
    exit 2
}
