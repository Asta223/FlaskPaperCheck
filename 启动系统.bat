@echo off
chcp 65001 >nul
title Factory Management System
cd /d "%~dp0"

echo ============================================================
echo  Factory Management System - One-click Start
echo ============================================================
echo  Step 1: deploy environment
echo  Step 2: start server and open browser
echo ============================================================
echo.

call "%~dp0deploy_env.bat"
if errorlevel 1 goto fail

call "%~dp0run_system.bat"
if errorlevel 1 goto fail
exit /b 0

:fail
echo.
echo [FAILED] See messages above.
pause >nul
exit /b 1
