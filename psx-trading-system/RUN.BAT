@echo off
setlocal
title PSX Live ^& Research
cd /d "%~dp0"
echo ==================================================
echo   PSX Live ^& Research  -  free, open-source, PSX
echo ==================================================
set PORT=8111
if not "%~1"=="" set PORT=%~1
if not "%PSX_PORT%"=="" set PORT=%PSX_PORT%

set PYCMD=
where py >nul 2>nul && set "PYCMD=py -3"
if defined PYCMD goto pyfound
where python >nul 2>nul && set "PYCMD=python"
if defined PYCMD goto pyfound
where python3 >nul 2>nul && set "PYCMD=python3"
if defined PYCMD goto pyfound
echo.
echo [ERROR] Python was not found on this PC.
echo Run INSTALL.BAT first - it tells you exactly what to install.
echo.
pause
exit /b 1

:pyfound
%PYCMD% --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo [ERROR] Python does not run - likely the Microsoft Store stub.
  echo Install real Python 3 from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH", then run INSTALL.BAT.
  echo.
  pause
  exit /b 1
)
echo Python found: %PYCMD%
echo [1/2] Checking free dependencies - fast after INSTALL...
%PYCMD% -m pip install -q -r requirements.txt
echo [2/2] Starting dashboard at http://127.0.0.1:%PORT% ...
echo        Phone on the same Wi-Fi:  http://YOUR-PC-IP:%PORT%
echo        Other port:  RUN.BAT 8005   or   set PSX_PORT=8005
echo        To stop:  run STOP.BAT or close this window.
echo.
rem Browser opens by itself AS SOON as the server answers (works on auto-start too)
start /min "" powershell -NoProfile -Command "for($i=0;$i -lt 90;$i++){try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 http://127.0.0.1:%PORT%/api/health | Out-Null; Start-Process http://127.0.0.1:%PORT%; exit}catch{Start-Sleep 1}}"
%PYCMD% -m uvicorn src.app.server:app --host 0.0.0.0 --port %PORT%
echo.
echo The dashboard server has stopped.
pause
exit /b 0
