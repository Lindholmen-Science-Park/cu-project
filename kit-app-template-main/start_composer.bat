@echo off
echo Starting Younite USD Composer...
echo ==================================

REM Check if we're in the right directory
if not exist "repo.bat" (
    echo ERROR: repo.bat not found. Please run this script from the kit-app-template-main directory.
    pause
    exit /b 1
)

REM Optional scene argument handling (if not already provided by caller)
if not defined YOUNITE_SCENE_NAME (
    if not "%~1"=="" (
        set "YOUNITE_SCENE_NAME=%~1"
        echo Scene argument detected: %YOUNITE_SCENE_NAME%
    ) else (
        echo No scene argument provided. Defaulting to main_scene.usda
    )
)

REM Step 1: Build
echo Building project...
call repo.bat build

if %ERRORLEVEL% neq 0 (
    echo Build failed!
    pause
    exit /b 1
)

echo Build completed successfully!
echo.

REM Step 2: Launch (elevator test extension: only when YOUNITE_KIT_EXTRA_ARGS is set by startcomposer_elevator_test.bat)
echo Launching USD Composer...
echo.

set "KIT_EXTRA_ARGS="
if defined YOUNITE_KIT_EXTRA_ARGS set "KIT_EXTRA_ARGS=%YOUNITE_KIT_EXTRA_ARGS%"

call repo.bat launch younite.usd_composer.kit -- --enable-crash-reporter --enable-memory-monitoring %KIT_EXTRA_ARGS% --exec "auto_load_mastah.py"

set LAUNCH_EXIT_CODE=%ERRORLEVEL%

if %LAUNCH_EXIT_CODE% equ 0 (
    echo USD Composer launched successfully!
    echo Press Ctrl+C to stop when done.
    pause
    exit /b 0
) else (
    echo Launch failed with exit code: %LAUNCH_EXIT_CODE%
    echo Try the following troubleshooting steps:
    echo    1. Restart your computer
    echo    2. Check available memory (need at least 8GB free)
    echo    3. Close other GPU-intensive applications
    echo    4. Update NVIDIA drivers
    echo    5. Run as administrator
    pause
    exit /b %LAUNCH_EXIT_CODE%
)
