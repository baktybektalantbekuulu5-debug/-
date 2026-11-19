@echo off
rem BEAMNG YOUTUBE FACTORY - automatic PC check. Double-click to run.
chcp 65001 >nul
cd /d "%~dp0"
title BEAMNG YOUTUBE FACTORY - PC check

set "PY="
where py >nul 2>nul && (py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul && set "PY=py -3")
if not defined PY where python >nul 2>nul && (python -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul && set "PY=python")
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

if not defined PY (
    echo [1/3] Installing Python 3.12 ...
    winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY (
    echo Python could not be installed automatically.
    echo Install Python 3.12 from https://www.python.org/downloads/ and run this file again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [2/3] Creating environment ...
    %PY% -m venv .venv || (echo venv failed & pause & exit /b 1)
)
echo [2/3] Installing libraries ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -e . || (echo pip failed & pause & exit /b 1)

echo [3/3] Checking PC and BeamNG.drive. Do not touch the mouse while the game is being tested.
".venv\Scripts\python.exe" -m bfactory.doctor
echo.
echo Done. The report is in projects\_doctor\report.txt
pause
