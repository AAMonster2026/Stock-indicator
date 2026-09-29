@echo off
setlocal
cd /d "%~dp0"
set PORT=8080

echo Checking port %PORT%...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
  echo Port %PORT% is busy. Stopping old process PID %%a ...
  taskkill /F /PID %%a >nul 2>&1
)

timeout /t 1 /nobreak >nul

echo Starting Personal Investment Watch server...
echo.
py server.py %PORT%
if errorlevel 1 (
  echo.
  echo Failed to start. Try running stop.bat first.
  pause
)
