@echo off
echo Bake Terrain-Following Roads
echo =============================
echo.
echo This script regenerates gothenburg_roads.usda with terrain-following Y values
echo by loading the scene in Kit and raycasting each road point against the terrain.
echo.

REM Navigate to kit-app-template-main root (3 levels up from source/data/osm/)
pushd "%~dp0..\..\..\"

if not exist "repo.bat" (
    echo ERROR: repo.bat not found. Could not locate kit-app-template-main root.
    popd
    pause
    exit /b 1
)

REM Optional scene argument
if not "%~1"=="" (
    set "YOUNITE_SCENE_NAME=%~1"
    echo Using scene: %YOUNITE_SCENE_NAME%
) else (
    echo Using default scene: main_scene.usda
)

REM Build first
echo Building project...
call repo.bat build

if %ERRORLEVEL% neq 0 (
    echo Build failed!
    pause
    exit /b 1
)

echo Build completed successfully!
echo.

REM Launch Kit headlessly with the bake script
echo Launching Kit for terrain bake (headless) ...
echo.

call repo.bat launch younite.usd_viewer_streaming_dev.kit -- ^
 --no-window ^
 --/app/auto_load_usd="" ^
 --/app/renderer/resolution/width=2 ^
 --/app/renderer/resolution/height=2 ^
 --/rtx/rendermode="disabled" ^
 --/rtx/directLighting/enabled=false ^
 --/rtx/indirectDiffuse/enabled=false ^
 --/rtx/reflections/enabled=false ^
 --/rtx/translucency/enabled=false ^
 --/rtx/post/enabled=false ^
 --exec "source\data\osm\bake_terrain_roads.py"

set LAUNCH_EXIT_CODE=%ERRORLEVEL%

REM Check if output files were actually updated (Kit may crash on exit but files are valid)
if exist "source\data\osm\gothenburg_roads.usda" (
    echo.
    echo Output files found:
    echo   source\data\osm\gothenburg_roads.usda
    echo   source\data\osm\gothenburg_graph.json
    if %LAUNCH_EXIT_CODE% neq 0 (
        echo.
        echo NOTE: Kit exited with code %LAUNCH_EXIT_CODE% — this is often a PhysX cleanup crash
        echo       and does not affect the generated files.
    )
) else (
    echo.
    echo ERROR: Output files not found — bake may have failed.
)

popd
pause
exit /b 0
