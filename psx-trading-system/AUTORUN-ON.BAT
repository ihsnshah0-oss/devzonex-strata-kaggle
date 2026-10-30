@echo off
setlocal enabledelayedexpansion
title PSX Live ^& Research - AUTORUN ON
cd /d "%~dp0"
echo ==================================================
echo   AUTO-RUN: start the dashboard automatically at
echo   every Windows start-up and open the browser.
echo   This happens ONLY because you ran this file.
echo   Undo at any time with AUTORUN-OFF.BAT.
echo ==================================================
rem NOTE: delayed expansion (!VBS!) is used on purpose - the folder name
rem may contain special characters like ^& and must not break the command.
set "VBS=%~dp0psx-autorun.vbs"
rem -- tiny VBScript: switch to this folder, start RUN.BAT minimized --
> "!VBS!" echo Set Wsh = CreateObject("WScript.Shell")
>> "!VBS!" echo Wsh.CurrentDirectory = "%~dp0"
>> "!VBS!" echo Wsh.Run "cmd /c RUN.BAT", 7, False
if not exist "!VBS!" (
  echo [ERROR] Could not create psx-autorun.vbs in this folder.
  pause
  exit /b 1
)
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "PSX Live and Research" /t REG_SZ /d "wscript.exe \"!VBS!\"" /f
if errorlevel 1 (
  echo.
  echo [ERROR] Could not write the start-up entry.
  echo Right-click AUTORUN-ON.BAT and choose "Run as administrator".
  echo.
  pause
  exit /b 1
)
echo.
echo Verifying the start-up entry:
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "PSX Live and Research"
echo.
echo AUTO-RUN is ON. From the next Windows start the dashboard starts by
echo itself (minimized) and the browser opens once the server is ready.
echo.
set /p TRYIT="Test it right now (starts the dashboard)? [Y/N]: "
if /i "!TRYIT!"=="Y" start "" wscript "!VBS!"
pause
exit /b 0
