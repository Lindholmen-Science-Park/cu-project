@echo off
echo ========================================
echo Goteverse Project Setup
echo ========================================
echo.

set "NUCLEUS_SKIPPED=0"

REM --- Step 0: Install Python dependencies for post-processing scripts ---
echo ----------------------------------------
echo Step 0: Installing Python dependencies
echo ----------------------------------------
echo.

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: 'python' was not found on PATH.
    echo        Install Python 3.10+ and ensure it is on PATH, then re-run preinstall.bat.
    exit /b 1
)

set "TOOLS_REQ=%~dp0kit-app-template-main\source\data\Assets\Tools\requirements.txt"
if exist "%TOOLS_REQ%" (
    echo Installing dependencies from:
    echo   %TOOLS_REQ%
    python -m pip install --disable-pip-version-check -r "%TOOLS_REQ%"
    if %ERRORLEVEL% neq 0 (
        echo WARNING: pip install failed — post-processing scripts may not run.
    ) else (
        echo OK: Python dependencies installed.
    )
) else (
    echo NOTE: No Tools\requirements.txt found — skipping pip install.
)
echo.

REM --- Step 1: Check .env ---
if not exist "%~dp0.env" (
    echo WARNING: .env file not found.
    echo          Copy .env.example to .env and fill in credentials.
    echo          Skipping Nucleus pull.
    echo.
    set "NUCLEUS_SKIPPED=1"
)

REM --- Step 2: Pull from Nucleus ---
if "%NUCLEUS_SKIPPED%"=="0" (
    echo ----------------------------------------
    echo Step 1: Pulling content from Nucleus
    echo ----------------------------------------
    echo.
    call "%~dp0pullnucleus.bat"
    if %ERRORLEVEL% neq 0 (
        echo.
        echo WARNING: Nucleus pull failed — continuing with existing local content.
        echo.
    )
)

REM --- Step 3: Run post-processing scripts ---
echo.
echo ----------------------------------------
echo Step 2: Running post-processing scripts
echo ----------------------------------------
echo.
call "%~dp0runscripts.bat"

echo.
echo ========================================
echo Setup complete.
if "%NUCLEUS_SKIPPED%"=="1" (
    echo NOTE: Nucleus pull was skipped — set up .env and run pullnucleus.bat manually.
)
echo ========================================
