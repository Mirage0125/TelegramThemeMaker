@echo off
setlocal
cd /d "%~dp0"
title Telegram Theme Maker - Installation Check

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Check-Install.ps1"
set "CHECK_RESULT=%ERRORLEVEL%"

echo.
if "%CHECK_RESULT%"=="0" (
    echo Checks completed. See logs\check-report.txt for the full report.
) else (
    echo Some checks failed. See logs\check-report.txt for details.
)
echo.
pause
exit /b %CHECK_RESULT%
