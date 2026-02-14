@echo off
setlocal EnableExtensions

set "PROJECT_DIR=%~dp0"
pushd "%PROJECT_DIR%" >nul 2>&1
if errorlevel 1 (
    echo Failed to open project folder.
    pause
    exit /b 1
)

echo ========================================================
echo   My LinkedIn Automation Request
echo   Date: 2026-02-14
echo ========================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo Python is not available in PATH.
    echo Install Python 3 and try again.
    popd
    pause
    exit /b 1
)

echo [1/3] Checking dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed.
    popd
    pause
    exit /b 1
)

echo.
echo [2/3] Validating configuration...
python -c "from config import config; errs = config.validate(); print('Config loaded successfully' if not errs else 'Config errors: ' + '; '.join(errs)); exit(0 if not errs else 1)"
if errorlevel 1 (
    echo Please fix your .env values and run again.
    popd
    pause
    exit /b 1
)

echo.
echo [3/3] Starting automation now...
python main.py --run-now
set "RUN_EXIT=%ERRORLEVEL%"

echo.
if "%RUN_EXIT%"=="0" (
    echo Script finished successfully.
) else (
    echo Script finished with errors. Exit code: %RUN_EXIT%
)

popd
echo.
pause
exit /b %RUN_EXIT%
