@echo off
setlocal
cd /d "%~dp0"

set "BOOTSTRAP="
if exist ".venv\Scripts\python.exe" goto have_venv

where py >nul 2>nul
if %errorlevel%==0 (
  set "BOOTSTRAP=py -3.11"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "BOOTSTRAP=python"
  ) else (
    echo Python was not found in PATH. Install Python 3.11+ or create .venv manually first.
    exit /b 1
  )
)

echo Virtual environment not found. Creating .venv...
call %BOOTSTRAP% -m venv .venv
if errorlevel 1 exit /b 1

:have_venv
if not exist ".venv\Scripts\python.exe" (
  echo Failed to create .venv. Check that Python is installed correctly.
  exit /b 1
)

echo Installing/updating dependencies...
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo.
echo Starting Rating UI on http://192.168.120.231:8081
echo Users in the same LAN should open: http://192.168.120.231:8081
echo.

call ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8081
