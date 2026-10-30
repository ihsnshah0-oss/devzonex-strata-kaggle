@echo off
setlocal
title PSX Live ^& Research - AUTORUN OFF
cd /d "%~dp0"
echo Removing the AUTO-RUN start-up entry...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "PSX Live and Research" /f >nul 2>nul
if exist "%~dp0psx-autorun.vbs" del "%~dp0psx-autorun.vbs"
echo.
echo Done. AUTO-RUN is OFF. The dashboard will no longer start by
echo itself when the PC boots. Use RUN.BAT to start it manually.
timeout /t 6 >nul
exit /b 0
