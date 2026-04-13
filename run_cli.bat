@echo off
setlocal EnableExtensions

cd /d "%~dp0"
chcp 65001 >nul

if not exist "venv\Scripts\activate.bat" (
  python -m venv venv
  call venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call venv\Scripts\activate.bat
)

pip show pyrogram >nul 2>nul
if errorlevel 1 (
  echo [TG Deleter] В venv нет pyrogram. Ставлю requirements.txt...
  pip install -r requirements.txt
)

python script.py --cli
exit /b %errorlevel%

