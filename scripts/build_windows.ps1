# Build a standalone BlackWall.exe (Windows, no Python installation required).
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = "python"
$venv = Join-Path $root ".venv-build"
if (-not (Test-Path -LiteralPath $venv)) {
    & $python -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt pyinstaller

& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name BlackWall `
    --icon (Join-Path $root "assets\icon.ico") `
    --add-data "assets;assets" `
    --collect-all yt_dlp `
    --collect-all imageio_ffmpeg `
    (Join-Path $root "main.py")

$built = Join-Path $root "dist\BlackWall.exe"
if (Test-Path -LiteralPath $built) {
    Copy-Item -LiteralPath $built -Destination (Join-Path $root "BlackWall.exe") -Force
    Write-Host "Built: $root\BlackWall.exe"
} else {
    throw "PyInstaller did not produce dist\BlackWall.exe"
}
