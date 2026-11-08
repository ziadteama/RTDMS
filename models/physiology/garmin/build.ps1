# Build a Connect IQ app in this folder for the Forerunner 265.
#
#   .\build.ps1                      # builds rr_check  -> rr_check\bin\rr_check.prg
#   .\build.ps1 -App rr_check -Device fr265s
#
# Needs: Java 17+, the Connect IQ SDK (installed by the SDK Manager, which records the active SDK
# in %APPDATA%\Garmin\ConnectIQ\current-sdk.cfg) with the device downloaded, and a developer key
# (default %USERPROFILE%\.garmin\developer_key.der, never committed).
param(
    [string]$App = "rr_check",
    [string]$Device = "fr265",
    [string]$Key = "$env:USERPROFILE\.garmin\developer_key.der"
)
$ErrorActionPreference = "Stop"

$cfg = Join-Path $env:APPDATA "Garmin\ConnectIQ\current-sdk.cfg"
if (-not (Test-Path $cfg)) { throw "No Connect IQ SDK found ($cfg). Install one with the SDK Manager." }
$sdk = (Get-Content $cfg -Raw).Trim()
$monkeyc = Join-Path $sdk "bin\monkeyc.bat"
if (-not (Test-Path $monkeyc)) { throw "monkeyc not found in $sdk" }
if (-not (Test-Path $Key)) { throw "Developer key not found: $Key" }

$project = Join-Path $PSScriptRoot $App
$out = Join-Path $project "bin\$App.prg"
New-Item -ItemType Directory -Force (Split-Path $out) | Out-Null
Write-Host "SDK: $sdk"
Write-Host "building $App for $Device -> $out"
# Run through cmd so monkeyc's warnings / errors (on stderr) are printed as plain lines and do
# not trip PowerShell's error handling; judge the build by its exit code only.
$jungle = Join-Path $project "monkey.jungle"
cmd /c "`"$monkeyc`" -d $Device -f `"$jungle`" -o `"$out`" -y `"$Key`" -w 2>&1"
if ($LASTEXITCODE -ne 0) { throw "monkeyc failed ($LASTEXITCODE)" }
Write-Host "OK: $out"
