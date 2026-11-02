@echo off
cd /d "%~dp0"
docker compose --profile dashboard --profile bench down
echo.
echo Stopped. Your database is kept. To delete it too, run:  docker compose down -v
pause
