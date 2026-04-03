@echo off
echo ==========================================
echo   SuperMew Backend Starter
echo ==========================================
echo.
set VENV_PATH=.venv_311\Scripts\python.exe

if not exist %VENV_PATH% (
    echo [ERROR] Virtual environment not found at .venv_311
    echo Please ensure the environment is set up.
    pause
    exit /b 1
)

echo [INFO] Starting FastAPI server...
%VENV_PATH% backend/app.py
pause
