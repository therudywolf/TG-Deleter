@echo off
cd /d "%~dp0"
chcp 65001 >nul 2>nul
title TG Deleter

where python >nul 2>nul
if errorlevel 1 goto :no_python

if exist "venv\Scripts\python.exe" goto :check_deps

echo [TG Deleter] Sozdayu venv...
python -m venv venv
if errorlevel 1 goto :venv_fail

:check_deps
venv\Scripts\pip.exe show pyrogram >nul 2>nul
if errorlevel 1 goto :install_deps
goto :run

:install_deps
echo [TG Deleter] Ustanavlivayu zavisimosti...
venv\Scripts\pip.exe install -r requirements.txt
if errorlevel 1 goto :deps_fail

:run
if /i "%~1"=="cli" goto :run_cli
echo [TG Deleter] GUI...
venv\Scripts\python.exe script.py
goto :check_exit

:run_cli
echo [TG Deleter] CLI...
venv\Scripts\python.exe script.py --cli %2 %3 %4 %5
goto :check_exit

:check_exit
if errorlevel 1 goto :app_fail
goto :end

:no_python
echo [ERROR] Python not found in PATH.
echo Install Python 3.10+ from https://python.org
pause
exit /b 1

:venv_fail
echo [ERROR] Failed to create venv.
pause
exit /b 1

:deps_fail
echo [ERROR] Failed to install dependencies.
pause
exit /b 1

:app_fail
echo.
echo [TG Deleter] Exit code: %errorlevel%
pause
exit /b 1

:end
