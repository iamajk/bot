@echo off
title Bot 1 - StrangerMeet
cd /d "%~dp0"

echo ============================================
echo  Bot 1 - Auto Setup ^& Launch
echo ============================================

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Python is not installed or not in PATH.
    echo Please download and install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

python -c "import playwright, anthropic" >nul 2>&1
if errorlevel 1 (
    echo [1/3] Installing dependencies...
    python -m pip install playwright anthropic
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Dependencies already installed — skipping.
)

if not exist "%USERPROFILE%\AppData\Local\ms-playwright" (
    echo [2/3] Installing Playwright browsers...
    python -m playwright install chromium
    if errorlevel 1 (
        echo ERROR: Failed to install Playwright browsers.
        pause
        exit /b 1
    )
) else (
    echo [2/3] Playwright browser already installed — skipping.
)

echo [3/3] Starting Bot 1...
echo ============================================
python main.py
pause
