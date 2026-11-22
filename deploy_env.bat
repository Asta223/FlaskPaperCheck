@echo off
chcp 65001 >nul
title Factory Management System - Deploy
cd /d "%~dp0"

set "PY=venv\Scripts\python.exe"

echo ============================================================
echo  Deploy / Build Runtime Environment
echo ============================================================
echo.

if not exist "%PY%" (
    echo [1/6] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 goto fail_venv
) else (
    echo [1/6] Virtual environment found.
)

echo [2/6] Installing dependencies...
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto fail_pip

if not exist ".env" (
    echo [3/6] Creating .env from .env.example...
    copy /Y ".env.example" ".env" >nul
    if errorlevel 1 goto fail_env
) else (
    echo [3/6] .env found.
)

echo [4/6] Ensuring database exists...
"%PY%" scripts\ensure_database.py
if errorlevel 1 goto fail_db_create

echo [5/6] Applying database migrations...
"%PY%" -m flask db upgrade
if errorlevel 1 goto fail_migrate

echo [6/6] Loading seed data...
"%PY%" scripts\seed.py
if errorlevel 1 goto fail_seed

echo.
echo [OK] Environment is ready.
echo      Run run_system.bat to start the server.
exit /b 0

:fail_venv
echo.
echo [ERROR] Failed to create virtual environment.
echo         Make sure Python 3 is installed and added to PATH.
goto fail

:fail_pip
echo.
echo [ERROR] Failed to install dependencies.
echo         Check your network connection or pip configuration.
goto fail

:fail_env
echo.
echo [ERROR] Failed to create .env from .env.example.
goto fail

:fail_db_create
echo.
echo [ERROR] Failed to ensure database exists.
echo         Check DB_* settings in .env and whether MySQL is running.
goto fail

:fail_migrate
echo.
echo [ERROR] Database migration failed.
echo         Check .env settings and the messages above.
goto fail

:fail_seed
echo.
echo [ERROR] Failed to load seed data. See messages above.
goto fail

:fail
echo.
echo [FAILED] Deployment stopped.
pause >nul
exit /b 1
