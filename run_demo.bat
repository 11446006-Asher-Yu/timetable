@echo off
rem ============================================================
rem  Campus Timetable - one-click local demo for Windows
rem  1. find Python 3.10+   2. create .venv   3. install packages
rem  4. create database + demo data   5. start server + open browser
rem ============================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"

echo [1/5] Looking for Python 3.10 or newer...
set "PY="
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [ERROR] Python 3.10 or newer was not found.
    echo         Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    goto fail
)
%PY% --version

if not exist ".venv\Scripts\python.exe" (
    echo [2/5] Creating virtual environment .venv ...
    %PY% -m venv .venv || goto fail
) else (
    echo [2/5] Using existing virtual environment .venv
)
set "VPY=.venv\Scripts\python.exe"

echo [3/5] Installing packages...
"%VPY%" -m pip install --disable-pip-version-check -q -r requirements.txt || goto fail

echo [4/5] Preparing database and demo data...
"%VPY%" manage.py migrate --noinput -v 0 || goto fail
"%VPY%" manage.py seed_demo || goto fail

echo [5/5] Starting server at http://127.0.0.1:8000/  (press Ctrl+C to stop)
if not defined NO_BROWSER start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000/"
"%VPY%" manage.py runserver 127.0.0.1:8000
goto end

:fail
echo.
echo [ERROR] Setup stopped. Please read the message above.
pause
exit /b 1

:end
endlocal
