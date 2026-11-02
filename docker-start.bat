@echo off
setlocal
cd /d "%~dp0"

docker --version >nul 2>nul
if errorlevel 1 goto :no_docker
docker info >nul 2>nul
if errorlevel 1 goto :not_running

echo.
echo Starting API, PostgreSQL and Redis.
echo The first run builds the image and takes a few minutes...
echo.
docker compose up -d --build --wait
if errorlevel 1 goto :failed

echo.
echo ==============================================
echo   Running!
echo   Web page   : http://localhost:5000
echo   API health : http://localhost:5000/health
echo   Logs       : docker compose logs -f api
echo   Stop       : docker-stop.bat
echo ==============================================
start "" http://localhost:5000/
echo.
pause
exit /b 0

:no_docker
echo [ERROR] Docker was not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop/
echo         restart your computer if asked, then run this file again.
goto :fail

:not_running
echo [ERROR] Docker is installed but not running. Open Docker Desktop, wait until it says
echo         "Engine running", then run this file again.
goto :fail

:failed
echo.
echo [ERROR] Something did not start. See the messages above, or run:  docker compose logs api
echo         If you changed POSTGRES_PASSWORD after the first run, reset the database with:
echo         docker compose down -v
goto :fail

:fail
echo.
pause
exit /b 1
