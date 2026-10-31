@echo off
rem BlackWall launcher: starts the app without a console window.
setlocal
set "PYDIR=C:\Users\ivano\AppData\Local\Python\pythoncore-3.15-64"
set "HERE=%~dp0"

if not exist "%PYDIR%\pythonw.exe" (
    echo BlackWall: Python was not found at %PYDIR%
    echo Edit this file or run "python main.py" manually.
    pause
    exit /b 1
)

start "" "%PYDIR%\pythonw.exe" "%HERE%main.py" %*
exit /b 0
