@echo off
rem BlackWall launcher: starts the app without a console window.
setlocal
set "HERE=%~dp0"

if exist "%HERE%BlackWall.exe" (
    start "" "%HERE%BlackWall.exe" %*
    exit /b 0
)

where pythonw.exe >nul 2>&1
if errorlevel 1 (
    echo BlackWall: Python was not found in PATH.
    echo Install Python or run the packaged BlackWall.exe.
    pause
    exit /b 1
)

start "" pythonw.exe "%HERE%main.py" %*
exit /b 0
