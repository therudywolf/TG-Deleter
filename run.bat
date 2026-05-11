@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul 2>nul
title TG Deleter

where python >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в PATH.
    echo Установите Python 3.10+ с https://python.org и отметьте "Add to PATH".
    pause
    exit /b 1
)

if not exist "venv\Scripts\activate.bat" (
    echo [TG Deleter] Создаю виртуальное окружение...
    python -m venv venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать venv.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

pip show pyrogram >nul 2>nul
if errorlevel 1 (
    echo [TG Deleter] Устанавливаю зависимости...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось установить зависимости.
        pause
        exit /b 1
    )
)

if /i "%~1"=="cli" (
    echo [TG Deleter] Запуск CLI...
    python script.py --cli %2 %3 %4 %5
) else (
    echo [TG Deleter] Запуск GUI...
    python script.py
)

if errorlevel 1 (
    echo.
    echo [TG Deleter] Приложение завершилось с ошибкой (код %errorlevel%).
    pause
)
