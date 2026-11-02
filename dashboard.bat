@echo off
setlocal
title Shortly dashboard
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Run start.bat first - it sets everything up.
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"

echo Checking packages - the first time this downloads Streamlit and can take a few minutes...
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Package installation failed. Read the red text above.
    pause
    exit /b 1
)

rem Streamlit asks for an e-mail address on its very first run; this answers it with "none".
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    mkdir "%USERPROFILE%\.streamlit" 2>nul
    (
        echo [general]
        echo email = ""
    ) > "%USERPROFILE%\.streamlit\credentials.toml"
)

if "%API_URL%"=="" set "API_URL=http://localhost:5000"
echo.
echo Dashboard: http://localhost:8501   ^(API: %API_URL%^)
echo Keep start.bat running in another window. Stop this one with Ctrl+C.
echo.
python -m streamlit run dashboard\app.py --server.port 8501

echo.
pause
