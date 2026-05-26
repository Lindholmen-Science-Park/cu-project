@echo off
setlocal enabledelayedexpansion
echo Starting Younite USD Viewer Streaming...
echo =============================================================

REM Optional scene argument handling (inherited from startstream.bat or passed as %~1)
if not defined YOUNITE_SCENE_NAME (
    if not "%~1"=="" (
        set "YOUNITE_SCENE_NAME=%~1"
        echo Scene argument detected: !YOUNITE_SCENE_NAME!
    )
)

REM Build --/app/auto_load_usd arg (default: main_scene.usda)
set "scene_name=main_scene.usda"
if defined YOUNITE_SCENE_NAME (
    set "scene_name=!YOUNITE_SCENE_NAME!"
    if not "!scene_name:~-5!"==".usda" set "scene_name=!scene_name!.usda"
    echo Loading scene: !scene_name!
) else (
    echo Using default scene: main_scene.usda
)
set "AUTO_LOAD_ARG=--/app/auto_load_usd=./source/data/scenes/!scene_name!"
echo.

if not exist "repo.bat" (
    echo ERROR: repo.bat not found. Run from kit-app-template-main.
    pause
    exit /b 1
)

echo Building project...
call repo.bat build
if %ERRORLEVEL% neq 0 (
    echo Build failed!
    pause
    exit /b 1
)
echo Build completed successfully!
echo.

echo Launching USD Viewer Streaming with RTX Geometry Streaming...
echo UJITSO LOD disabled (full-quality geometry for walkthrough experience).
echo.

REM Set the trained model to use
if "%MODEL%"=="" set MODEL=llama3.1-younite
echo Using AI model: %MODEL%
echo.

call repo.bat launch younite.usd_viewer_streaming_dev.kit -- ^
 !AUTO_LOAD_ARG! ^
 --no-window ^
 --enable-crash-reporter ^
 --enable-memory-monitoring ^
 --enable omni.ujitso.client ^
 --/rtx/hydra/geometrystreaming/enabled=true ^
 --/UJITSO/enabled=false ^
 --/persistent/UJITSO/geometry=false

set "LAUNCH_EXIT_CODE=!ERRORLEVEL!"

if !LAUNCH_EXIT_CODE! equ 0 (
    echo USD Viewer Streaming launched successfully!
    echo WebRTC Server: 127.0.0.1:49100 ^(signaling^), 49101 ^(media^)
    echo Press Ctrl+C to stop when done.
    pause
    exit /b 0
) else (
    echo Launch failed with exit code: !LAUNCH_EXIT_CODE!
    echo Try:
    echo   1) Restart PC
    echo   2) Ensure >= 8GB free RAM
    echo   3) Close GPU-intensive apps
    echo   4) Update NVIDIA drivers
    echo   5) Run as admin
    pause
    exit /b !LAUNCH_EXIT_CODE!
)
