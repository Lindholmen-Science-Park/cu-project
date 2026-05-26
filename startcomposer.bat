@echo off
echo ========================================
echo Starting Younite USD Composer
echo ========================================
echo.

REM Elevator extension loads only via startcomposer_elevator_test.bat (not this script).
if /i not "%~1"=="elevator_test_scene" set "YOUNITE_KIT_EXTRA_ARGS="

REM Optional argument: scene name (without extension) to open from source/data/scenes
IF NOT "%~1"=="" (
    set "YOUNITE_SCENE_NAME=%~1"
    echo Scene argument detected: %YOUNITE_SCENE_NAME%
) ELSE (
    echo No scene argument provided. Defaulting to main_scene.usda
)

REM Navigate to kit-app-template-main and run Composer
echo Starting Composer...
cd kit-app-template-main
call start_composer.bat
cd ..

REM Clean up environment variable in current shell
IF DEFINED YOUNITE_SCENE_NAME (
    set "YOUNITE_SCENE_NAME="
)

echo.
echo ========================================
echo USD Composer process completed
echo ========================================
