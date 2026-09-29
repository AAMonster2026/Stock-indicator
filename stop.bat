@echo off
setlocal
set PORT=8080

echo Stopping servers on port %PORT%...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
  echo Ending process PID %%a
  taskkill /F /PID %%a >nul 2>&1
)

timeout /t 1 /nobreak >nul
echo Done. You can now run start.bat
