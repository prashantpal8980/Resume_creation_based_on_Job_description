@echo off
echo ==========================================
echo   ResumeForge - One-Time Setup
echo ==========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

:: Create virtual environment
if not exist "venv" (
    echo [1/4] Creating virtual environment...
    python -m venv venv
) else (
    echo [1/4] Virtual environment already exists.
)

:: Activate and install dependencies
echo [2/4] Installing Python dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt

:: Install Playwright browsers
echo [3/4] Installing Playwright Chromium...
playwright install chromium

:: Create directories
echo [4/4] Creating required directories...
if not exist "uploads" mkdir uploads
if not exist "generated" mkdir generated
if not exist "history" mkdir history

:: Create .env if not exists
if not exist ".env" (
    copy .env.example .env
    echo [INFO] Created .env from .env.example - please verify your Chrome profile path.
)

echo.
echo ==========================================
echo   Setup Complete!
echo.
echo   IMPORTANT: Verify your Chrome profile path in .env
echo   To find it: Open Chrome ^> chrome://version/
echo   Look for "Profile Path"
echo.
echo   To start the app, run: start.bat
echo ==========================================
pause
