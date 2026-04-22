@echo off
echo ==========================================
echo   ResumeForge - AI Resume Builder
echo ==========================================
echo.
echo   NOTE: Chrome will be launched separately
echo   with a dedicated debug profile.
echo   Your regular Chrome can stay open!
echo.

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Start Flask server
echo   Starting ResumeForge server...
echo   Open http://localhost:5000 in your browser.
echo.
python app.py
