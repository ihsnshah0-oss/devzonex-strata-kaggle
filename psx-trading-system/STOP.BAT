@echo off
setlocal
title PSX Live ^& Research - STOP
echo Stopping the PSX Live ^& Research dashboard...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*uvicorn*src.app.server*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo.
echo Done. The server is stopped. Browser tabs will show no data
echo until RUN.BAT starts it again.
timeout /t 6 >nul
exit /b 0
