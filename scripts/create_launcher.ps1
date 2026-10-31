# Create a BlackWall-named Windows launcher so Task Manager shows "BlackWall"
# instead of "pythonw.exe". Run from the project folder:
#   powershell -ExecutionPolicy Bypass -File .\scripts\create_launcher.ps1
param(
    [string]$Python = "pythonw.exe"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pythonw = (Get-Command $Python -ErrorAction Stop).Source
$pythonDir = Split-Path -Parent $pythonw
$launcher = Join-Path $pythonDir "BlackWall.exe"

if (-not (Test-Path -LiteralPath $launcher)) {
    New-Item -ItemType HardLink -Path $launcher -Target $pythonw | Out-Null
    Write-Host "Created $launcher"
} else {
    Write-Host "Using existing $launcher"
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcut = Join-Path $desktop "BlackWall.lnk"
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcut)
$link.TargetPath = $launcher
$link.Arguments = "`"$root\main.py`""
$link.WorkingDirectory = $root
$link.Description = "BlackWall — live wallpapers"
$link.Save()
Write-Host "Shortcut updated: $shortcut"
