@echo off
setlocal
title URL Shortener
cd /d "%~dp0"

echo.
echo ==============================================
echo   URL Shortener - one-click start
echo ==============================================
echo.

rem ---------- 1. Python ----------
python --version >nul 2>nul
if errorlevel 1 goto :no_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto :old_python

rem ---------- 2. Virtual environment ----------
if not exist ".venv\Scripts\activate.bat" (
    echo [1/4] Creating virtual environment - first run only...
    python -m venv .venv
    if errorlevel 1 goto :venv_failed
)
call ".venv\Scripts\activate.bat"

rem ---------- 3. Settings file ----------
if not exist ".env" echo [2/4] Creating .env settings file...
python scripts\setup_env.py
if errorlevel 1 goto :env_failed

rem ---------- 4. Packages (reinstalled automatically when requirements.txt changes) ----------
for /f %%h in ('python scripts\req_hash.py') do set "REQ_HASH=%%h"
set "OLD_HASH="
if exist ".venv\.req_hash" set /p OLD_HASH=<".venv\.req_hash"
if not "%REQ_HASH%"=="%OLD_HASH%" (
    echo [3/4] Installing packages - this can take a few minutes...
    python -m pip install --disable-pip-version-check -r requirements-dev.txt
    if errorlevel 1 goto :pip_failed
    >".venv\.req_hash" echo %REQ_HASH%
)

rem ---------- 5. Database tables ----------
echo [4/4] Preparing the database...
alembic upgrade head
if errorlevel 1 goto :db_failed

rem ---------- 6. Run ----------
echo.
echo ==============================================
echo   Open  http://localhost:5000
echo   Stop with   Ctrl+C   ^(answer Y if asked^)
echo ==============================================
echo.
start "" cmd /c "timeout /t 4 /nobreak >nul & start http://localhost:5000/"
python -m flask --app app.main:create_app run --debug --port 5000

echo.
echo Server stopped.
pause
exit /b 0

:no_python
echo [ERROR] Python was not found.
echo         Install Python 3.11 or newer from https://www.python.org/downloads/
echo         and tick "Add python.exe to PATH" in the installer. Then run start.bat again.
goto :fail

:old_python
echo [ERROR] Your Python is too old. This project needs Python 3.11 or newer.
echo         Install a newer version from https://www.python.org/downloads/
goto :fail

:venv_failed
echo [ERROR] Could not create the virtual environment.
goto :fail

:env_failed
echo [ERROR] Could not create the .env file. Make sure .env.example exists in this folder.
goto :fail

:pip_failed
echo [ERROR] Package installation failed. Read the red text above, fix it, and run start.bat again.
goto :fail

:db_failed
echo [ERROR] Database setup failed. Read the error above.
echo         If it mentions SECRET_KEY or settings, delete the .env file and run start.bat again.
goto :fail

:fail
echo.
pause
exit /b 1
