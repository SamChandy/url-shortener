@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
    echo Run start.bat first - it sets everything up.
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"
python scripts\try_analytics.py
echo.
pause
