# Copy a built .prg onto a Garmin watch connected by USB (sideloading, no Connect IQ Store).
#
#   .\sideload.ps1                         # rr_check\bin\rr_check.prg -> watch GARMIN\Apps
#   .\sideload.ps1 -Prg path\to\app.prg
#
# The Forerunner 265 connects as a media (MTP) device, not a drive letter, so the copy goes
# through the Windows Shell. Unplug the watch afterwards; the app then appears in its app list
# (hold UP / Menu > Apps, or the activity list).
param(
    [string]$Prg = (Join-Path $PSScriptRoot "rr_check\bin\rr_check.prg")
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Prg)) { throw "Not built yet: $Prg (run .\build.ps1)" }

$shell = New-Object -ComObject Shell.Application
$watch = $shell.NameSpace(17).Items() | Where-Object { $_.Name -match "Forerunner|Garmin" } |
    Select-Object -First 1
if (-not $watch) { throw "No Garmin watch under This PC - plug it in by USB and unlock it." }

# Walk: <watch> \ <storage, e.g. "Internal Storage" or "Primary"> \ GARMIN \ Apps
function Child($folder, $name) {
    $folder.Items() | Where-Object { $_.Name -eq $name } | Select-Object -First 1
}
$storage = $watch.GetFolder.Items() | Select-Object -First 1
$garmin = Child $storage.GetFolder "GARMIN"
if (-not $garmin) { throw "GARMIN folder not found on $($watch.Name)" }
$apps = Child $garmin.GetFolder "Apps"
if (-not $apps) { throw "GARMIN\Apps not found on $($watch.Name)" }

$name = Split-Path $Prg -Leaf
$size = (Get-Item $Prg).Length
Write-Host "copying $name -> $($watch.Name)\$($storage.Name)\GARMIN\Apps"
$apps.GetFolder.CopyHere((Resolve-Path $Prg).Path, 16)  # 16 = answer "yes" to overwrite
# MTP copies are asynchronous: wait until the file is on the watch at full size. The Shell
# lists it without its extension ("rr_check", not "rr_check.prg").
$stem = [IO.Path]::GetFileNameWithoutExtension($name)
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    $f = $apps.GetFolder.Items() | Where-Object { $_.Name -in @($name, $stem) } |
        Select-Object -First 1
    if ($f -and [long]$f.ExtendedProperty("Size") -eq $size) {
        Write-Host "OK: $name is on the watch ($size bytes). Unplug it."
        exit 0
    }
}
throw "Copy did not finish within 30 s"
