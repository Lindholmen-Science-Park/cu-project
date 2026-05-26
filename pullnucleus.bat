@echo off
echo ========================================
echo Pulling Latest Content from Nucleus
echo ========================================
echo.

REM Load credentials from .env
if exist "%~dp0.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0.env") do (
        set "%%A=%%B"
    )
) else (
    echo ERROR: .env file not found — Nucleus credentials are not set.
    echo        Copy .env.example to .env and fill in the values.
    exit /b 1
)

if "%NUCLEUS_SERVER%"=="" (
    echo ERROR: NUCLEUS_SERVER not set in .env
    exit /b 1
)

echo Nucleus server: %NUCLEUS_SERVER%
echo.

REM Build Kit SDK if needed (ensures Python + omni.client are available)
echo Building Kit SDK if needed...
cd kit-app-template-main
call repo.bat build
if %ERRORLEVEL% neq 0 (
    echo ERROR: Kit SDK build failed!
    cd ..
    exit /b 1
)

REM Find Kit executable
set "KIT_EXE=_build\windows-x86_64\release\kit\kit.exe"
if not exist "%KIT_EXE%" (
    echo ERROR: Kit executable not found at %KIT_EXE%
    echo        Ensure the build completed successfully.
    cd ..
    exit /b 1
)

echo.
echo Running Nucleus sync...
echo.

REM Run pullnucleus.py via Kit with the base app profile.
REM The base .kit loads the full extension stack (including omni.client).
REM Overrides prevent loading any USD scene — Kit starts, runs the sync, and exits.
"%KIT_EXE%" ^
    "source\apps\younite.usd_viewer_streaming_base.kit" ^
    --ext-folder "source\extensions" ^
    --ext-folder "source\apps" ^
    --exec "pullnucleus.py" ^
    --no-window ^
    --/app/auto_load_usd="" ^
    --/app/content/emptyStageOnStart=true ^
    --/app/fastShutdown=true ^
    --/app/livestream/skipCapture=1 ^
    --/app/livestream/webrtc/enabled=false

set PULL_EXIT=%ERRORLEVEL%
cd ..

if %PULL_EXIT% neq 0 (
    echo.
    echo WARNING: Nucleus pull completed with errors (exit code %PULL_EXIT%)
    exit /b %PULL_EXIT%
)

echo.
echo ========================================
echo SUCCESS: Nucleus pull complete
echo ========================================
