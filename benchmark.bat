@echo off
setlocal
cd /d "%~dp0"

docker info >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Docker is not running. Start Docker Desktop first.
    pause
    exit /b 1
)
if not exist "benchmark_results" mkdir "benchmark_results"

echo.
echo ===== Run 1 of 2: WITH the Redis cache =====
set "CACHE_ENABLED=true"
set "BENCH_LABEL=with_redis"
docker compose up -d --force-recreate --wait api
if errorlevel 1 goto :failed
docker compose --profile bench run --rm locust
if errorlevel 1 goto :failed

echo.
echo ===== Run 2 of 2: WITHOUT the cache (every redirect reads PostgreSQL) =====
set "CACHE_ENABLED=false"
set "BENCH_LABEL=without_redis"
docker compose up -d --force-recreate --wait api
if errorlevel 1 goto :failed
docker compose --profile bench run --rm locust
if errorlevel 1 goto :failed

echo.
echo Restoring the normal configuration...
set "CACHE_ENABLED=true"
docker compose up -d --force-recreate --wait api

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\summarize_benchmark.py
) else (
    python scripts\summarize_benchmark.py
)
echo.
pause
exit /b 0

:failed
echo.
echo [ERROR] The benchmark stopped. Read the messages above (try: docker compose logs api).
pause
exit /b 1
