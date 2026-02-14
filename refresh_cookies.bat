@echo off
REM Quick Cookie Refresh Helper
echo.
echo ========================================
echo   LinkedIn Cookie Refresh Helper
echo ========================================
echo.
echo This will help you update expired LinkedIn cookies.
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ first
    pause
    exit /b 1
)

REM Run the cookie refresher
python src\cookie_refresher.py

echo.
echo ========================================
echo.
pause
