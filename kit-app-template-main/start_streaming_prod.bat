@echo off
setlocal enabledelayedexpansion
echo Starting Younite USD Viewer Streaming (PRODUCTION extension set)...
echo =============================================================

REM Optional scene argument handling (inherited from startstream_prod.bat or passed as %~1)
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

echo Launching PRODUCTION streaming app (no dev/CU-only extensions).
echo.

REM Local younite.* extensions live under _build\...\exts (not on kit/prod registries).
REM Without --ext-folder, the dependency solver only sees registries and fails on e.g. younite.distance_culling_extension.
set "KIT_RELEASE_ROOT=%~dp0_build\windows-x86_64\release"
if not exist "%KIT_RELEASE_ROOT%\exts\younite.distance_culling_extension" (
    echo ERROR: Built extensions not found at:
    echo   %KIT_RELEASE_ROOT%\exts
    echo Run `repo.bat build` from this folder and ensure the build completes.
    pause
    exit /b 1
)

call repo.bat launch younite.usd_viewer_streaming_base.kit -- ^
 !AUTO_LOAD_ARG! ^
 --ext-folder "%KIT_RELEASE_ROOT%\exts" ^
 --ext-folder "%KIT_RELEASE_ROOT%\apps" ^
 --no-window ^
 --enable-crash-reporter ^
 --enable-memory-monitoring ^
 --enable omni.ujitso.client ^
 --/rtx/hydra/geometrystreaming/enabled=true ^
 --/UJITSO/enabled=false ^
 --/persistent/UJITSO/geometry=false

set "LAUNCH_EXIT_CODE=!ERRORLEVEL!"

if !LAUNCH_EXIT_CODE! equ 0 (
    echo USD Viewer Streaming ^(prod^) launched successfully!
    echo WebRTC Server: 127.0.0.1:49100 ^(signaling^), 49101 ^(media^)
    echo Press Ctrl+C to stop when done.
    pause
    exit /b 0
) else (
    echo Launch failed with exit code: !LAUNCH_EXIT_CODE!
    pause
    exit /b !LAUNCH_EXIT_CODE!
)
