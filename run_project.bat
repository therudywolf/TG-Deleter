@echo off
setlocal EnableExtensions

REM Универсальный запускатор:
REM run_project.bat        -> GUI
REM run_project.bat cli   -> CLI

cd /d "%~dp0"
chcp 65001 >nul

if /i "%~1"=="cli" goto :run_cli
goto :run_gui

:ensure_venv
if not exist "venv\Scripts\activate.bat" (
  python -m venv venv
  call venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call venv\Scripts\activate.bat
)
exit /b 0

:run_cli
call :ensure_venv
python script.py --cli
exit /b %errorlevel%

:run_gui
call :ensure_venv
python script.py
exit /b %errorlevel%

