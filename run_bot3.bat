@echo off
title Bot 3 - StrangerMeet
cd /d "%~dp0\Bot3"

echo ============================================
echo  Bot 3 - Auto Setup ^& Launch
echo ============================================

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not installed. Download from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Python found. Installing dependencies...
python -m pip install playwright anthropic
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

echo [3/3] Starting Bot 3...
echo ============================================
python main.py
pause
