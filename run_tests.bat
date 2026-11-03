@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title FlyRank Widget Platform - one-click tests

REM Usage:  run_tests.bat            live end-to-end suite against the running Docker stack (default)
REM         run_tests.bat all        unit tests + live suite + the 6 acceptance probes
REM         run_tests.bat unit       only the existing unit tests (inside the api container)
REM         run_tests.bat probes     only scripts/run_probes.py (adds a few rows to the demo widget)
REM         run_tests.bat local      run the live suite with a local Python instead of Docker

set MODE=%~1
if "%MODE%"=="" set MODE=live
set RC=0

echo.
echo ============================================================
echo  FlyRank Widget Platform - automated verification  [%MODE%]
echo ============================================================

if /i "%MODE%"=="local" goto :local

docker info >nul 2>&1
if errorlevel 1 (
  echo [X] Docker is not running. Start Docker Desktop, wait for "Engine running", then try again.
  set RC=2
  goto :end
)
docker compose ps --status running --services 2>nul | findstr /i "api" >nul
if errorlevel 1 (
  echo [X] The stack is not running. In another window run:  docker compose up --build
  echo     Wait for "Application startup complete", seed once ^(docker compose exec api python -m scripts.seed^), then re-run this.
  set RC=2
  goto :end
)

if /i "%MODE%"=="unit"   goto :unit
if /i "%MODE%"=="probes" goto :probes
if /i "%MODE%"=="all"    goto :unit
goto :live

:unit
echo.
echo --- [1] Unit tests (existing tests/ folder, inside the api container) ---
docker compose exec -T api python -m pytest -q tests
if errorlevel 1 set RC=1
if /i "%MODE%"=="unit" goto :end

:live
echo.
echo --- Live end-to-end suite (takes about 2 minutes: it respects the API's rate limits) ---
docker compose run --rm -T --no-deps -v "%CD%\livetests:/livetests" ^
  -e LIVE_BASE_URL=http://api:8000 -e LIVE_SITE_URL=http://customer-site:5500 -e LIVE_ORIGIN=http://localhost:5500 ^
  api python -m pytest -c /livetests/pytest.ini --rootdir=/livetests /livetests
if errorlevel 1 set RC=1
if /i "%MODE%"=="all" goto :probes
goto :report

:probes
echo.
echo --- Acceptance probes 1-6 (scripts/run_probes.py) ---
docker compose exec -T api python -m scripts.run_probes --base http://localhost:8000
if errorlevel 1 set RC=1
goto :report

:local
where python >nul 2>&1
if errorlevel 1 (
  echo [X] Python not found on PATH. Use the default Docker mode ^(run_tests.bat^) instead.
  set RC=2
  goto :end
)
if not exist ".venv-livetests\Scripts\python.exe" (
  echo Creating .venv-livetests ...
  python -m venv .venv-livetests
)
".venv-livetests\Scripts\python.exe" -m pip install -q -r livetests\requirements.txt
if errorlevel 1 ( set RC=2 & goto :end )
".venv-livetests\Scripts\python.exe" -m pytest -c livetests\pytest.ini --rootdir=livetests livetests
if errorlevel 1 set RC=1

:report
if exist "livetests\report\report.html" (
  echo.
  echo Report: %CD%\livetests\report\report.html
  start "" "livetests\report\report.html"
)

:end
echo.
if "%RC%"=="0" (echo RESULT: ALL GOOD) else if "%RC%"=="1" (echo RESULT: SOME CHECKS FAILED - open the report for details) else (echo RESULT: COULD NOT RUN - see message above)
if not "%NOPAUSE%"=="1" pause
exit /b %RC%
