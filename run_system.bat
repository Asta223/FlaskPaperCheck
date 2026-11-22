@echo off
chcp 65001 >nul
title Factory Management System - Running
cd /d "%~dp0"

set "PY=venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [ERROR] Virtual environment not found.
    echo         Run deploy_env.bat first.
    pause >nul
    exit /b 1
)

echo ============================================================
echo  Factory Management System - Running
echo ============================================================
echo  The default browser will open automatically.
echo  Press Ctrl+C or close this window to stop the server.
echo ============================================================
echo.

"%PY%" start_server.py
if errorlevel 1 goto fail
exit /b 0

:fail
echo.
echo [ERROR] Server stopped with an error. See messages above.
pause >nul
exit /b 1
