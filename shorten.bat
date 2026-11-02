@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\shorten.py
) else (
    python scripts\shorten.py
)
echo.
pause
