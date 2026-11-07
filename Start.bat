@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title Telegram Theme Maker

REM This launcher never downloads or installs Python.
REM It uses an already installed compatible Python 3.10-3.14.

if not exist ".venv\Scripts\python.exe" (
    echo Searching for an installed compatible Python version...
    set "PYTHON_CMD="

    REM Prefer the Python install manager / launcher.
    for %%V in (3.14 3.13 3.12 3.11 3.10) do (
        py -V:%%V --version >nul 2>&1
        if not errorlevel 1 (
            if not defined PYTHON_CMD set "PYTHON_CMD=py -V:%%V"
        )
    )

    REM Fall back to the ordinary python command if the launcher is unavailable.
    if not defined PYTHON_CMD (
        python --version >nul 2>&1
        if not errorlevel 1 (
            python -c "import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,15) else 1)" >nul 2>&1
            if not errorlevel 1 set "PYTHON_CMD=python"
        )
    )

    if not defined PYTHON_CMD (
        echo.
        echo Python 3.10-3.14 was not found.
        echo This launcher does NOT download or install Python.
        echo Install Python 3.14 manually, then run Start.bat again.
        echo https://www.python.org/downloads/release/python-3140/
        echo.
        pause
        exit /b 1
    )

    echo Found: !PYTHON_CMD!
    echo [1/3] Creating the virtual environment...
    !PYTHON_CMD! -m venv .venv
    if errorlevel 1 (
        echo.
        echo Could not create the virtual environment.
        echo Check that the selected Python installation includes the venv module.
        pause
        exit /b 1
    )
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,15) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo The existing .venv uses a Python version outside 3.10-3.14.
        echo Delete the .venv folder and run Start.bat again to recreate it.
        pause
        exit /b 1
    )
)

echo [2/3] Checking required libraries...
".venv\Scripts\python.exe" -c "import aiogram, PIL, dotenv, aiohttp" >nul 2>&1
if errorlevel 1 (
    echo Core libraries are missing; installing the initial environment...
    ".venv\Scripts\python.exe" -m pip --disable-pip-version-check install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Could not install libraries. Check your internet connection.
        pause
        exit /b 1
    )
) else (
    echo Base environment is ready; dependency updates are handled by the updater.
)

if not exist ".env" (
    copy "config.example.env" ".env" >nul
    echo.
    echo Created .env. Open it and paste your Telegram bot token after BOT_TOKEN=.
    notepad ".env"
    echo Save the file, close Notepad, then run Start.bat again.
    pause
    exit /b 0
)

echo [3/3] Starting bot...
".venv\Scripts\python.exe" BackgroundRunner.py
echo.
echo Bot stopped. If there is an error above, take a screenshot.
pause
