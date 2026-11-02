@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
    echo Run start.bat first - it sets everything up.
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m pip install --disable-pip-version-check -q -r requirements-dev.txt
if errorlevel 1 (
    echo [ERROR] Package installation failed.
    pause
    exit /b 1
)
python -m pytest %*
echo.
pause
