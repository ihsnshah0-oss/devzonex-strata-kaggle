@echo off
setlocal
title PSX Live ^& Research - INSTALL
cd /d "%~dp0"
echo ==================================================
echo   PSX Live ^& Research  -  one-time INSTALL
echo ==================================================
set PYCMD=
where py >nul 2>nul && set "PYCMD=py -3"
if defined PYCMD goto pyfound
where python >nul 2>nul && set "PYCMD=python"
if defined PYCMD goto pyfound
where python3 >nul 2>nul && set "PYCMD=python3"
if defined PYCMD goto pyfound
echo.
echo [ERROR] Python was not found on this PC.
echo Please install Python 3 from https://www.python.org/downloads/
echo IMPORTANT: tick the box "Add python.exe to PATH" during install,
echo then run INSTALL.BAT again.
echo.
pause
exit /b 1

:pyfound
%PYCMD% --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo [ERROR] A python shortcut was found but it does not run.
  echo This usually means the Microsoft Store stub, not real Python.
  echo Install Python 3 from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH", then run INSTALL.BAT again.
  echo.
  pause
  exit /b 1
)
echo Python found: %PYCMD%
echo Installing or updating all free dependencies - please wait...
%PYCMD% -m pip install --upgrade pip
%PYCMD% -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo [ERROR] Package install failed. Check your internet connection,
  echo then run INSTALL.BAT again.
  echo.
  pause
  exit /b 1
)
echo.
echo INSTALL complete. From now on just double-click RUN.BAT.
pause
exit /b 0
