@echo off
echo ========================================================
echo   LinkedIn Cookie Refresher (Telegram-Interactive)
echo ========================================================
echo.
echo This will open a browser, log into LinkedIn, and
echo update your .env file with a fresh li_at cookie.
echo.
echo You will receive Telegram messages guiding you through
echo the process (including OTP if needed).
echo.

echo [1/2] Checking dependencies...
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo Error installing dependencies!
    pause
    exit /b 1
)

echo.
echo [2/2] Starting Telegram Login Flow...
echo.

python telegram_login.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Cookie refresh failed. See above for details.
    pause
) else (
    echo.
    echo Cookie refreshed! You can now run the automation:
    echo   python main.py --run-now
    echo   (or double-click run_now.bat)
    timeout /t 10
)
