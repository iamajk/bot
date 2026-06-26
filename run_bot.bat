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

echo [1/3] Python found. Installing dependencies...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

echo [2/3] Installing Playwright browsers...
python -m playwright install chromium
if errorlevel 1 (
    echo ERROR: Failed to install Playwright browsers.
    pause
    exit /b 1
)

echo [3/3] Starting Bot 1...
echo ============================================
python main.py
pause
