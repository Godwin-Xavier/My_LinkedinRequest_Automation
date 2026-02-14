@echo off
echo ========================================================
echo   LinkedIn Recruiter Outreach Automation - Manual Run
echo   Date: 2026-02-14
echo ========================================================
echo.

echo [1/3] Checking dependencies...
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo Error installing dependencies!
    pause
    exit /b 1
)

echo.
echo [2/3] Validating configuration...
python -c "from config import config; print('Config loaded successfully')"
if %ERRORLEVEL% NEQ 0 (
    echo Error parsing configuration. Please check your .env file!
    echo Ensure LINKEDIN_LI_AT is set correctly.
    pause
    exit /b 1
)

echo.
echo [3/3] Starting Automation...
echo Running with --run-now flag (Immediate Execution)
echo.

python main.py --run-now

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Script finished with errors.
    pause
) else (
    echo.
    echo Script finished successfully.
    timeout /t 10
)
